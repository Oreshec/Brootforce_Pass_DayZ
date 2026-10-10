#!/usr/bin/env python3
"""
Брутфорс импульсного замка. Механика H1: колёса независимы,
зажатие = +1 только колесу в фокусе.

Чистый CPython, ноль pip-зависимостей.
    Ввод:      SendInput + KEYEVENTF_SCANCODE (скан-коды видят DirectInput/RawInput)
    Остановка: Ctrl+C (или Ctrl+1, перехватывается, в игру не попадает)

Запуск:
    python Brootforce_Pass_DayZ2.py --test               # игра видит ввод?
    python Brootforce_Pass_DayZ2.py --probe "h0.6"       # один шаг вручную
    python Brootforce_Pass_DayZ2.py                      # боевой прогон

Как крутит:
    Одометр. Каждый шаг = +1 ко всему коду. Единицы всегда получают
    своё зажатие. Если единицы переполнились (было 9) — старшим колёсам
    тоже даётся по зажатию, по одному, с возвратом фокуса на единицы.
    Никакого «прокрутить все 10 цифр и переехать на старший разряд».
"""
from __future__ import annotations

import argparse
import ctypes
import random
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Protocol

# ============================ WinAPI ============================

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0

_EXTRA_SCAN = {"esc": 0x01, "tab": 0x0F, "enter": 0x1C, "space": 0x39,
               "up": 0x48, "left": 0x4B, "right": 0x4D, "down": 0x50}
_EXTENDED = {"up", "left", "right", "down"}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
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


def scan_code(key: str) -> int:
    k = key.strip().lower()
    if k in _EXTRA_SCAN:
        return _EXTRA_SCAN[k]
    if k == " ":
        return 0x39
    if len(k) == 1 and k.isalnum():
        code = user32.MapVirtualKeyW(ord(k.upper()), MAPVK_VK_TO_VSC)
        if code:
            return code
    raise ValueError(f"Неизвестен скан-код для клавиши {key!r}")


def _send_scancode(key: str, up: bool) -> None:
    flags = KEYEVENTF_SCANCODE
    if key.lower() in _EXTENDED:
        flags |= 0x0001
    if up:
        flags |= KEYEVENTF_KEYUP
    item = _INPUT(type=INPUT_KEYBOARD)
    item.ki = _KEYBDINPUT(wVk=0, wScan=scan_code(key), dwFlags=flags)
    if user32.SendInput(1, (_INPUT * 1)(item), ctypes.sizeof(_INPUT)) != 1:
        raise OSError(f"SendInput failed, GetLastError={ctypes.get_last_error()}")


# ============================ КОНФИГУРАЦИЯ ============================

@dataclass(frozen=True)
class CrackerConfig:
    digits_count: int = 4
    interact_key: str = "f"
    step_time: float = 0.6          # зажатие = +1 цифра (калибровка!)
    start_code: int = 0
    pause: tuple[float, float] = (0.05, 0.1)
    press_time: tuple[float, float] = (0.02, 0.04)

    @property
    def total_codes(self) -> int:
        return 10 ** self.digits_count

    def __post_init__(self) -> None:
        if self.digits_count < 1:
            raise ValueError("digits_count должен быть >= 1")
        if self.step_time <= 0:
            raise ValueError("step_time должен быть > 0")
        if not 0 <= self.start_code < self.total_codes:
            raise ValueError("start_code вне диапазона")


# ============================ ОТМЕНА ============================

class OperationCancelled(Exception):
    pass


class CancellationToken:
    def __init__(self) -> None:
        import threading
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
        if self._event.wait(seconds):
            raise OperationCancelled()

    def sleep_precise(self, seconds: float) -> None:
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


# ============================ ВВОД ============================

class KeyActor(Protocol):
    def click(self, key: str) -> None: ...
    def hold(self, key: str, duration: float) -> None: ...
    def release_all(self) -> None: ...


class SendInputKeyActor:
    def __init__(self, config: CrackerConfig, token: CancellationToken) -> None:
        self._config = config
        self._token = token
        self._pressed: set[str] = set()

    def click(self, key: str) -> None:
        self._token.check()
        _send_scancode(key, up=False)
        self._pressed.add(key)
        try:
            self._token.sleep_precise(random.uniform(*self._config.press_time))
        finally:
            self._safe_release(key)

    def hold(self, key: str, duration: float) -> None:
        self._token.check()
        _send_scancode(key, up=False)
        self._pressed.add(key)
        try:
            self._token.sleep_precise(duration)
        finally:
            self._safe_release(key)

    def _safe_release(self, key: str) -> None:
        try:
            _send_scancode(key, up=True)
        except OSError:
            pass
        finally:
            self._pressed.discard(key)

    def release_all(self) -> None:
        for key in list(self._pressed):
            self._safe_release(key)


class DryRunKeyActor:
    def __init__(self, config: CrackerConfig, token: CancellationToken) -> None:
        self._config = config
        self._token = token

    def click(self, key: str) -> None:
        self._token.check()

    def hold(self, key: str, duration: float) -> None:
        self._token.check()

    def release_all(self) -> None:
        pass


# ============================ ВРАЩЕНИЕ ============================

def carry_levels(code: int) -> int:
    """Сколько старших колёс нужно докрутить при +1 к code.
    0->0 (0), 9->1 (1), 99->2 (2), 19->1 (1)."""
    levels = 0
    while code % 10 == 9:
        levels += 1
        code //= 10
    return levels


class Odometer:
    """Один шаг = +1 ко всему коду. Фокус всегда возвращается на единицы."""

    def __init__(self, config: CrackerConfig, keys: KeyActor,
                 token: CancellationToken) -> None:
        self._config = config
        self._keys = keys
        self._token = token

    def run(self) -> None:
        cfg = self._config
        code = cfg.start_code
        while code < cfg.total_codes - 1:
            self._token.check()
            self._step(code)
            code += 1

    def _step(self, code: int) -> None:
        cfg = self._config
        key = cfg.interact_key

        # единицы всегда +1
        self._keys.hold(key, cfg.step_time)
        self._pause()

        # старшие колёса, если единицы переполнились
        levels = carry_levels(code)
        for _ in range(levels):
            self._keys.click(key)
            self._pause()
            self._keys.hold(key, cfg.step_time)
            self._pause()

        # возврат фокуса на единицы: клик идёт только к старшим с заворотом,
        # поэтому назад со старшего колеса нужно (N - levels) кликов
        for _ in range(cfg.digits_count - levels):
            self._keys.click(key)
            self._pause()

    def _pause(self) -> None:
        self._token.sleep(random.uniform(*self._config.pause))


# ============================ ПРОБНИК ============================

_PROBE_CLICK = ("c", "к")
_PROBE_HOLD = ("h", "з")
_PROBE_PAUSE = ("p", "п")


def parse_probe_sequence(seq: str) -> list[tuple[str, float]]:
    actions: list[tuple[str, float]] = []
    for raw in seq.replace(",", " ").split():
        tok = raw.strip().lower()
        if not tok:
            continue
        kind, arg = tok[0], tok[1:]
        try:
            value = float(arg) if arg else None
        except ValueError:
            raise ValueError(f"после {kind!r} ожидалось число, получено {raw!r}")
        if kind in _PROBE_CLICK:
            actions.append(("click", 0.0))
        elif kind in _PROBE_HOLD:
            actions.append(("hold", 1.0 if value is None else value))
        elif kind in _PROBE_PAUSE:
            actions.append(("pause", 0.3 if value is None else value))
        else:
            raise ValueError(f"неизвестный токен {raw!r} (допустимы c/к, h/з, p/п)")
    if not actions:
        raise ValueError("последовательность пуста")
    return actions


def run_probe(actor: KeyActor, config: CrackerConfig, token: CancellationToken,
              sequence: str, pause: float) -> None:
    actions = parse_probe_sequence(sequence)
    pretty = " ".join("click" if k == "click" else f"{k}({v:.2f}s)"
                      for k, v in actions)
    print(f"ПРОБНИК: {pretty}")
    print("Переключитесь в игру.")
    for index, (kind, value) in enumerate(actions, 1):
        token.check()
        print(f"  [{index}/{len(actions)}] {kind} {value:.2f}с")
        if kind == "click":
            actor.click(config.interact_key)
        elif kind == "hold":
            actor.hold(config.interact_key, value)
        else:
            token.sleep(value)
        if pause > 0 and index < len(actions):
            token.sleep(pause)
    print("ПРОБНИК: завершено.")


# ============================ СЛУЖЕБНОЕ ============================

def run_input_test(actor: KeyActor, config: CrackerConfig,
                   token: CancellationToken) -> None:
    print("ТЕСТ ВВОДА: 3 клика и зажатие 1 с — смотрите на реакцию игры.")
    for _ in range(3):
        actor.click(config.interact_key)
        token.sleep(0.4)
    actor.hold(config.interact_key, 1.0)
    print("Тест завершён. Если игра отреагировала — запускайте без --test.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Брутфорс импульсного замка")
    p.add_argument("--digits", type=int, default=None)
    p.add_argument("--key", default=None)
    p.add_argument("--start-code", type=int, default=None)
    p.add_argument("--step-time", type=float, default=None,
                   help="зажатие = +1 цифра, с (по умолчанию 0.6)")
    p.add_argument("--probe", default=None, metavar="SEQ")
    p.add_argument("--probe-pause", type=float, default=0.3)
    p.add_argument("--test", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def build_config(args: argparse.Namespace) -> CrackerConfig:
    specified: dict[str, object] = {}
    if args.digits is not None:
        specified["digits_count"] = args.digits
    if args.key is not None:
        specified["interact_key"] = args.key
    if args.start_code is not None:
        specified["start_code"] = args.start_code
    if args.step_time is not None:
        specified["step_time"] = args.step_time
    return CrackerConfig(**specified)


def main() -> None:
    args = parse_args()
    try:
        config = build_config(args)
    except ValueError as exc:
        print(f"[!] Некорректные параметры: {exc}")
        sys.exit(2)

    if args.probe is not None:
        try:
            parse_probe_sequence(args.probe)
        except ValueError as exc:
            print(f"[!] Плохой --probe: {exc}")
            sys.exit(2)

    try:
        scan_code(config.interact_key)
    except ValueError as exc:
        print(f"[!] {exc}")
        return

    token = CancellationToken()
    actor: KeyActor
    if args.dry_run:
        actor = DryRunKeyActor(config, token)
    else:
        actor = SendInputKeyActor(config, token)

    try:
        if args.probe is not None:
            run_probe(actor, config, token, args.probe, args.probe_pause)
        elif args.test:
            run_input_test(actor, config, token)
        else:
            print(f"ПОЕХАЛИ: {config.total_codes} кодов, шаг "
                  f"{config.step_time:.2f}с. Ctrl+C — стоп.\n")
            Odometer(config, actor, token).run()
            print("Все коды пройдены.")
    except OperationCancelled:
        print("\nОстановлено.")
    except KeyboardInterrupt:
        print("\nПрервано Ctrl+C.")
    finally:
        actor.release_all()


if __name__ == "__main__":
    main()
