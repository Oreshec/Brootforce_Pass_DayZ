"""
Автоматический перебор комбинаций импульсного замка.

Архитектура (composition root — main()):
    CrackerConfig       -- неизменяемая конфигурация (данные + валидация)
    CancellationToken   -- потокобезопасная отмена (Ctrl+1 / Ctrl+C)
    Logger              -- логирование с таймстампами
    KeyActor (Protocol) -- абстракция клавиатуры (DIP)
    PynputKeyActor      -- реализация через pynput
    LockCracker         -- бизнес-логика перебора (SRP)
    StopHotkeyListener  -- горячая клавиша остановки (SRP)
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pynput import keyboard


# ============================ КОНФИГУРАЦИЯ ============================

@dataclass(frozen=True)
class CrackerConfig:
    """Неизменяемые параметры брутфорса с валидацией."""

    digits_count: int = 6                        # цифр в замке
    interact_key: str = "f"                      # клавиша взаимодействия
    full_rotation_time: float = 5.13             # полный оборот разряда (10 цифр)
    start_block: int = 0                         # начальный блок десятков
    delay_between_actions: tuple[float, float] = (0.05, 0.1)
    click_press_time: tuple[float, float] = (0.02, 0.04)
    countdown_seconds: int = 5
    stop_hotkey: str = "<ctrl>+1"

    @property
    def one_digit_time(self) -> float:
        """Время проворота на 1 цифру (~0.513 с)."""
        return self.full_rotation_time / 10.0

    @property
    def total_blocks(self) -> int:
        """Количество блоков по 10 комбинаций (для 6 цифр = 100 000)."""
        return 10 ** (self.digits_count - 1)

    def __post_init__(self) -> None:
        if self.digits_count < 2:
            raise ValueError("digits_count должен быть >= 2")
        if self.full_rotation_time <= 0:
            raise ValueError("full_rotation_time должен быть > 0")
        if not 0 <= self.start_block < self.total_blocks:
            raise ValueError("start_block вне допустимого диапазона")


# ============================ ОТМЕНА ОПЕРАЦИИ ============================

class OperationCancelled(Exception):
    """Сигнал об остановке скрипта (Ctrl+1 или Ctrl+C)."""


class CancellationToken:
    """Потокобезопасный токен отмены (замена глобальной is_running).

    Ожидания прерываются мгновенно при cancel() — даже во время зажатия.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def check(self) -> None:
        if self.cancelled:
            raise OperationCancelled()

    def sleep(self, seconds: float) -> None:
        """Прерываемая пауза: при cancel() немедленно выбрасывает исключение."""
        if self._event.wait(timeout=seconds):
            raise OperationCancelled()


# ============================ ЛОГИРОВАНИЕ ============================

class Logger:
    """Консольное логирование с таймстампами (SRP: только вывод)."""

    def __init__(self) -> None:
        self._start_time: float | None = None

    def start_timer(self) -> None:
        self._start_time = time.perf_counter()

    def _timestamp(self) -> str:
        now = datetime.now()
        elapsed = (
            f"+{time.perf_counter() - self._start_time:.2f}s"
            if self._start_time is not None else "+0.00s"
        )
        return f"[{now:%H:%M:%S}.{now.microsecond // 1000:03d} | {elapsed}]"

    def info(self, message: str) -> None:
        print(f"{self._timestamp()} {message}")

    def action(self, message: str) -> None:
        print(f"  {self._timestamp()} {message}")

    def banner(self, config: CrackerConfig) -> None:
        print(f"=== БРУТФОРС {config.digits_count}-ЗНАЧНОГО ЗАМКА (ИМПУЛЬСНЫЙ 0-9) ===")
        print(f"Экстренная остановка: {config.stop_hotkey} или Ctrl+C")


# ============================ УПРАВЛЕНИЕ КЛАВИАТУРОЙ ============================

class KeyActor(Protocol):
    """Абстракция над клавиатурой (инверсия зависимостей).

    Позволяет подменить реальный ввод заглушкой в тестах.
    """

    def click(self, key: str) -> None: ...
    def hold(self, key: str, duration: float) -> None: ...


class PynputKeyActor:
    """Реализация KeyActor на pynput. Один контроллер на весь запуск."""

    def __init__(self, config: CrackerConfig, logger: Logger, token: CancellationToken) -> None:
        self._config = config
        self._logger = logger
        self._token = token
        self._controller = keyboard.Controller()

    def click(self, key: str) -> None:
        self._token.check()
        self._controller.press(key)
        try:
            self._token.sleep(random.uniform(*self._config.click_press_time))
        finally:
            self._controller.release(key)
        self._logger.action(f"[КЛИК] '{key}'")

    def hold(self, key: str, duration: float) -> None:
        self._token.check()
        started = time.perf_counter()
        self._controller.press(key)
        try:
            self._token.sleep(duration)
        finally:
            self._controller.release(key)  # клавиша не «залипнет» при остановке
        actual = time.perf_counter() - started
        self._logger.action(f"[ЗАЖАТИЕ] '{key}' на {actual:.3f}сек (план: {duration:.3f}сек)")


# ============================ БИЗНЕС-ЛОГИКА ============================

def calculate_overflow_depth(block: int) -> int:
    """Глубина переноса при переходе из блока десятков в следующий.

    Глубина = число «хвостовых» девяток в блоке + 1.
    Примеры: 0 -> 1 (глубина 1), 9 -> 10 (глубина 2), 99 -> 100 (глубина 3).
    """
    depth = 1
    value = block
    while value % 10 == 9:
        depth += 1
        value //= 10
    return depth


class LockCracker:
    """Алгоритм перебора комбинаций (SRP: только бизнес-логика).

    Ничего не знает о pynput и глобальном состоянии — работает через абстракции.
    """

    def __init__(self, config: CrackerConfig, keys: KeyActor,
                 logger: Logger, token: CancellationToken) -> None:
        self._config = config
        self._keys = keys
        self._logger = logger
        self._token = token

    def run(self) -> None:
        cfg = self._config
        for block in range(cfg.start_block, cfg.total_blocks):
            self._token.check()
            self._process_block(block)
            self._pause()

    def _process_block(self, block: int) -> None:
        cfg = self._config
        prefix = f"{block:0{cfg.digits_count - 1}d}"
        self._logger.info(
            f"[БЛОК {block + 1}/{cfg.total_blocks}] Диапазон: [{prefix}0 ... {prefix}9]"
        )

        # Единственное зажатие: младший разряд прокручивается 0 -> 9
        self._keys.hold(cfg.interact_key, cfg.full_rotation_time)
        self._pause()

        if block + 1 < cfg.total_blocks:
            self._carry_over(block)

    def _carry_over(self, block: int) -> None:
        """Перенос разряда и возврат фокуса на младший разряд."""
        cfg = self._config
        depth = calculate_overflow_depth(block)
        self._logger.action(f"[ПЕРЕНОС] Смена блока десятков. Глубина: {depth}")

        self._repeat_clicks(depth)                       # фокус на старший разряд
        self._keys.hold(cfg.interact_key, cfg.one_digit_time)  # +1 к разряду
        self._pause()

        remaining = cfg.digits_count - depth
        self._logger.action(f"[ФОКУС] Возврат на 1-й разряд ({remaining} кликов)")
        self._repeat_clicks(remaining)

    def _repeat_clicks(self, count: int) -> None:
        for _ in range(count):
            self._keys.click(self._config.interact_key)
            self._pause()

    def _pause(self) -> None:
        self._token.sleep(random.uniform(*self._config.delay_between_actions))


# ============================ ГОРЯЧАЯ КЛАВИША ============================

class StopHotkeyListener:
    """Фоновый слушатель горячей клавиши остановки (SRP)."""

    def __init__(self, token: CancellationToken, hotkey: str, logger: Logger) -> None:
        self._token = token
        self._hotkey = hotkey
        self._logger = logger

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self._listen, daemon=True, name="stop-hotkey")
        thread.start()
        return thread

    def _listen(self) -> None:
        with keyboard.GlobalHotKeys({self._hotkey: self._on_stop}) as listener:
            listener.join()

    def _on_stop(self) -> None:
        if not self._token.cancelled:
            self._logger.info(f"[!] Остановка по {self._hotkey}...")
            self._token.cancel()


# ============================ ТОЧКА ВХОДА ============================

def _countdown(logger: Logger, token: CancellationToken, seconds: int) -> None:
    logger.info(f"Старт через {seconds} секунд...")
    for i in range(seconds, 0, -1):
        logger.info(f"{i}...")
        token.sleep(1)


def main() -> None:
    # Композиционный корень: все зависимости собираются в одном месте (DIP)
    config = CrackerConfig()
    token = CancellationToken()
    logger = Logger()

    logger.banner(config)
    StopHotkeyListener(token, config.stop_hotkey, logger).start()

    keys: KeyActor = PynputKeyActor(config, logger, token)
    cracker = LockCracker(config, keys, logger, token)

    try:
        _countdown(logger, token, config.countdown_seconds)
        logger.start_timer()
        logger.info("ПОЕХАЛИ!\n")
        cracker.run()
        logger.info("Перебор завершён: все блоки обработаны.")
    except OperationCancelled:
        logger.info("Остановлено по запросу пользователя.")
    except KeyboardInterrupt:
        logger.info("\nПрервано Ctrl+C.")


if __name__ == "__main__":
    main()
