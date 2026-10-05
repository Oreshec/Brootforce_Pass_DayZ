#!/usr/bin/env python3
"""
Брутфорс импульсного замка — чистый CPython, ноль pip-зависимостей.

Ввод:      SendInput + KEYEVENTF_SCANCODE — скан-коды видят DirectInput /
           Raw Input-игры, которые игнорируют виртуальные события pynput.
Остановка: Ctrl+1 через хук WH_KEYBOARD_LL (тоже ctypes).
Точность:  timeBeginPeriod(1) + прерываемый точный сон (~±1–2 мс).

Запуск:
    python lock_cracker.py --test     # проверить, видит ли игра ввод
    python lock_cracker.py --dry-run  # прогон логики без реального ввода
    python lock_cracker.py            # рабочий режим (лучше от администратора)
"""
from __future__ import annotations

import argparse
import ctypes
import random
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

# ============================ WinAPI ============================

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
VK_CONTROL = 0x11
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN, WM_QUIT = 0x0100, 0x0104, 0x0012


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    # нужен в union только ради корректного sizeof(INPUT) на x64
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT

_SCAN_EXTRA = {"esc": 0x01, "tab": 0x0F, "enter": 0x1C, "space": 0x39,
               "up": 0x48, "left": 0x4B, "right": 0x4D, "down": 0x50}
_EXTENDED_KEYS = {"up", "left", "right", "down"}


def scan_code(key: str) -> int:
    """Скан-код Set 1 — то, что читают DirectInput-игры."""
    k = key.strip().lower()
    if k in _SCAN_EXTRA:
        return _SCAN_EXTRA[k]
    if k == " ":
        return 0x39
    if len(k) == 1 and k.isalnum():
        code = user32.MapVirtualKeyW(ord(k.upper()), MAPVK_VK_TO_VSC)
        if code:
            return code
    raise ValueError(f"Неизвестен скан-код для клавиши {key!r}")


def _send_scancode(key: str, up: bool) -> None:
    flags = KEYEVENTF_SCANCODE
    if key.lower() in _EXTENDED_KEYS:
        flags |= KEYEVENTF_EXTENDEDKEY
    if up:
        flags |= KEYEVENTF_KEYUP
    item = _INPUT(type=INPUT_KEYBOARD)
    item.ki = _KEYBDINPUT(wVk=0, wScan=scan_code(key), dwFlags=flags)
    if user32.SendInput(1, (_INPUT * 1)(item), ctypes.sizeof(_INPUT)) != 1:
        raise OSError(f"SendInput failed, GetLastError={ctypes.get_last_error()}")


# ============================ КОНФИГУРАЦИЯ ============================

@dataclass(frozen=True)
class CrackerConfig:
    digits_count: int = 6
    interact_key: str = "f"
    full_rotation_time: float = 5.13
    start_block: int = 0
    delay_between_actions: tuple[float, float] = (0.05, 0.1)
    click_press_time: tuple[float, float] = (0.02, 0.04)
    countdown_seconds: int = 5

    @property
    def one_digit_time(self) -> float:
        return self.full_rotation_time / 10.0

    @property
    def total_blocks(self) -> int:
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
    """Остановка скрипта (Ctrl+1 или Ctrl+C)."""


class CancellationToken:
    """Потокобезопасная отмена. Все паузы прерываются мгновенно."""

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
        """Прерываемая пауза (точность ~5–15 мс) — для задержек между действиями."""
        if self._event.wait(seconds):
            raise OperationCancelled()

    def sleep_precise(self, seconds: float) -> None:
        """Прерываемый точный сон (~±1–2 мс) — для таймингов зажатий."""
        deadline = time.perf_counter() + seconds
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return
            self.check()
            if remaining > 0.005:
                if self._event.wait(min(remaining - 0.004, 0.02)):
                    raise OperationCancelled()
            else:
                time.sleep(0.001)


# ============================ ЛОГИРОВАНИЕ ============================

class Logger:
    def __init__(self) -> None:
        self._start: float | None = None

    def start_timer(self) -> None:
        self._start = time.perf_counter()

    def _ts(self) -> str:
        now = datetime.now()
        elapsed = f"+{time.perf_counter() - self._start:.2f}s" if self._start is not None else "+0.00s"
        return f"[{now:%H:%M:%S}.{now.microsecond // 1000:03d} | {elapsed}]"

    def info(self, msg: str) -> None:
        print(f"{self._ts()} {msg}")

    def action(self, msg: str) -> None:
        print(f"  {self._ts()} {msg}")

    def banner(self, config: CrackerConfig) -> None:
        print(f"=== БРУТФОРС {config.digits_count}-ЗНАЧНОГО ЗАМКА (SendInput, скан-коды) ===")
        print("Экстренная остановка: Ctrl + 1 или Ctrl+C")


# ============================ АКТЁРЫ ВВОДА ============================

class KeyActor(Protocol):
    def click(self, key: str) -> None: ...
    def hold(self, key: str, duration: float) -> None: ...
    def release_all(self) -> None: ...


class SendInputKeyActor:
    """Отправка скан-кодов через SendInput. release() всегда в finally."""

    def __init__(self, config: CrackerConfig, logger: Logger, token: CancellationToken) -> None:
        self._config = config
        self._logger = logger
        self._token = token
        self._pressed: set[str] = set()

    def click(self, key: str) -> None:
        self._token.check()
        _send_scancode(key, up=False)
        self._pressed.add(key)
        try:
            self._token.sleep_precise(random.uniform(*self._config.click_press_time))
        finally:
            _send_scancode(key, up=True)
            self._pressed.discard(key)
        self._logger.action(f"[КЛИК] '{key}'")

    def hold(self, key: str, duration: float) -> None:
        self._token.check()
        started = time.perf_counter()
        _send_scancode(key, up=False)
        self._pressed.add(key)
        try:
            self._token.sleep_precise(duration)
        finally:
            _send_scancode(key, up=True)
            self._pressed.discard(key)
        actual = time.perf_counter() - started
        self._logger.action(
            f"[ЗАЖАТИЕ] '{key}' {actual:.3f}с (план {duration:.3f}с, "
            f"Δ{(actual - duration) * 1000:+.1f} мс)"
        )

    def release_all(self) -> None:
        for key in list(self._pressed):
            try:
                _send_scancode(key, up=True)
            except OSError:
                pass
            self._pressed.discard(key)


class DryRunKeyActor:
    """Ничего не отправляет — проверка логики и отладка."""

    def __init__(self, config: CrackerConfig, logger: Logger, token: CancellationToken) -> None:
        self._config = config
        self._logger = logger
        self._token = token

    def click(self, key: str) -> None:
        self._token.check()
        self._logger.action(f"[DRY] [КЛИК] '{key}'")

    def hold(self, key: str, duration: float) -> None:
        self._token.check()
        self._logger.action(f"[DRY] [ЗАЖАТИЕ] '{key}' {duration:.3f}с")
        self._token.sleep(min(duration, 0.05))

    def release_all(self) -> None:
        pass


# ============================ БИЗНЕС-ЛОГИКА ============================

def calculate_overflow_depth(block: int) -> int:
    """Глубина переноса = число хвостовых девяток в блоке + 1 (0→1, 9→2, 99→3)."""
    depth = 1
    while block % 10 == 9:
        depth += 1
        block //= 10
    return depth


class LockCracker:
    """Алгоритм перебора. Не знает о вводе и ОС — только абстракции."""

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
        self._logger.info(f"[БЛОК {block + 1}/{cfg.total_blocks}] Диапазон: [{prefix}0 ... {prefix}9]")

        self._keys.hold(cfg.interact_key, cfg.full_rotation_time)  # 0 → 9
        self._pause()

        if block + 1 < cfg.total_blocks:
            self._carry_over(block)

    def _carry_over(self, block: int) -> None:
        cfg = self._config
        depth = calculate_overflow_depth(block)
        self._logger.action(f"[ПЕРЕНОС] Глубина: {depth}")

        self._repeat_clicks(depth)                                # фокус на старший разряд
        self._keys.hold(cfg.interact_key, cfg.one_digit_time)     # +1 к разряду
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


# ============================ ОСТАНОВКА: Ctrl+1 ============================

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HMODULE, wintypes.DWORD)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class StopHotkeyListener:
    """Ctrl+1 через WH_KEYBOARD_LL: работает в любом окне, «проглатывает»
    нажатие, чтобы игра его не получила. Ноль зависимостей."""

    def __init__(self, token: CancellationToken, logger: Logger, hotkey_vk: int = 0x31) -> None:
        self._token = token
        self._logger = logger
        self._hotkey_vk = hotkey_vk  # 0x31 = '1'
        self._thread_id = 0
        self._hook: wintypes.HHOOK | None = None
        self._proc = HOOKPROC(self._on_event)  # держим ссылку — иначе GC убьёт колбэк

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self._run, daemon=True, name="stop-hotkey")
        thread.start()
        return thread

    def _on_event(self, ncode: int, wparam: int, lparam: int) -> int:
        if ncode == 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            info = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if info.vkCode == self._hotkey_vk and self._ctrl_down() and not self._token.cancelled:
                self._logger.info("[!] Остановка по Ctrl+1...")
                self._token.cancel()
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
                return 1  # проглотить — игра не увидит Ctrl+1
        return user32.CallNextHookEx(None, ncode, wparam, lparam)

    def _ctrl_down(self) -> bool:
        return bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            self._logger.info(f"[!] Не удалось установить хук: {ctypes.get_last_error()}")
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(self._hook)


# ============================ СЛУЖЕБНОЕ ============================

def warn_if_not_admin(logger: Logger) -> None:
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        return
    logger.info("[!] Нет прав администратора. Если игра запущена с ними же (UIPI),")
    logger.info("    ввод будет заблокирован — перезапустите терминал от имени администратора.")


def enable_precise_timer() -> None:
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)  # тик 1 мс: точность сна ±1–2 мс
    except Exception:
        pass


def disable_precise_timer() -> None:
    try:
        ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass


def run_input_test(actor: KeyActor, config: CrackerConfig,
                   logger: Logger, token: CancellationToken) -> None:
    logger.info("ТЕСТ ВВОДА: 3 клика и зажатие 1 сек — смотрите на реакцию игры.")
    for _ in range(3):
        actor.click(config.interact_key)
        token.sleep(0.4)
    actor.hold(config.interact_key, 1.0)
    logger.info("Тест завершён. Если игра отреагировала — запускайте без --test.")


def _countdown(logger: Logger, token: CancellationToken, seconds: int) -> None:
    logger.info(f"Старт через {seconds} секунд... (переключитесь в окно игры!)")
    for i in range(seconds, 0, -1):
        logger.info(f"{i}...")
        token.sleep(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Брутфорс импульсного замка (чистый CPython, SendInput/скан-коды)")
    parser.add_argument("--digits", type=int, default=6, help="количество цифр замка")
    parser.add_argument("--key", default="f", help="клавиша взаимодействия")
    parser.add_argument("--start-block", type=int, default=0, help="начальный блок десятков")
    parser.add_argument("--test", action="store_true", help="проверка ввода: 3 клика + зажатие 1 сек")
    parser.add_argument("--dry-run", action="store_true", help="без реального ввода — только лог")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = CrackerConfig(digits_count=args.digits, interact_key=args.key,
                           start_block=args.start_block)
    token = CancellationToken()
    logger = Logger()

    logger.banner(config)
    warn_if_not_admin(logger)
    enable_precise_timer()
    sys.setswitchinterval(0.001)  # GIL освобождается чаще — хук отзывчивее

    StopHotkeyListener(token, logger).start()

    actor: KeyActor
    if args.dry_run:
        actor = DryRunKeyActor(config, logger, token)
        logger.info("Режим DRY-RUN: реальный ввод не отправляется.")
    else:
        actor = SendInputKeyActor(config, logger, token)

    try:
        if args.test:
            run_input_test(actor, config, logger, token)
        else:
            _countdown(logger, token, config.countdown_seconds)
            logger.start_timer()
            logger.info("ПОЕХАЛИ!\n")
            LockCracker(config, actor, logger, token).run()
            logger.info("Все блоки обработаны.")
    except OperationCancelled:
        logger.info("Остановлено по запросу пользователя.")
    except KeyboardInterrupt:
        logger.info("\nПрервано Ctrl+C.")
    finally:
        actor.release_all()
        disable_precise_timer()


if __name__ == "__main__":
    main()
