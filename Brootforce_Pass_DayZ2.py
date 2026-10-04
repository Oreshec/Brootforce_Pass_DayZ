import time
import random
import sys
import threading
from datetime import datetime
from pynput import keyboard

# ================= КОНФИГУРАЦИЯ =================
DIGITS_COUNT = 6                    # Количество цифр в замке
KEY_INTERACT = 'f'                  # Клавиша взаимодействия

FULL_ROTATION_TIME = 5.13           # Полный оборот разряда (10 цифр) за 1 зажатие
ONE_DIGIT_TIME = FULL_ROTATION_TIME / 10.0  # ~0.513 сек на 1 цифру для переносных разрядов

START_TEN_BLOCK = 0                 # Начальный блок десятков (0 = 000000..000009)
DELAY_BETWEEN_ACTIONS = (0.05, 0.1) # Задержка между кликами
# ================================================

is_running = True
start_time = None

def get_ts():
    """Возвращает метку времени с миллисекундами"""
    now = datetime.now()
    elapsed = f"{(time.time() - start_time):.2f}s" if start_time else "0.00s"
    return f"[{now.strftime('%H:%M:%S')}.{now.microsecond // 1000:03d} | +{elapsed}]"

def stop_script():
    global is_running
    print(f"\n{get_ts()} [!] Остановка по Ctrl + 1...")
    is_running = False

def start_hotkey_listener():
    with keyboard.GlobalHotKeys({'<ctrl>+1': stop_script}) as h:
        h.join()

def sleep_rnd(min_s, max_s):
    if not is_running:
        sys.exit(0)
    time.sleep(random.uniform(min_s, max_s))

def hold_key(key, duration):
    """Зажатие клавиши с логированием"""
    if not is_running:
        sys.exit(0)
    
    controller = keyboard.Controller()
    t_start = time.time()
    controller.press(key)
    time.sleep(duration)
    controller.release(key)
    t_actual = time.time() - t_start
    print(f"  {get_ts()} -> [ЗАЖАТИЕ] '{key}' на {t_actual:.3f}сек (план: {duration:.3f}сек)")

def click_key(key):
    """Одиночный клик клавиши"""
    if not is_running:
        sys.exit(0)
        
    controller = keyboard.Controller()
    controller.press(key)
    time.sleep(random.uniform(0.02, 0.04))
    controller.release(key)
    print(f"  {get_ts()} -> [КЛИК] '{key}'")

def get_code_str(step):
    return f"{step:0{DIGITS_COUNT}d}"

def calculate_overflow(prev_block, curr_block):
    """
    Вычисляет, сколько старших разрядов изменилось между блоками десятков
    Пример: block 0 (00000_) -> block 1 (00001_): глубина 1 (изменился 2-й разряд)
    Пример: block 9 (00009_) -> block 10 (00010_): глубина 2 (изменились 2-й и 3-й разряды)
    """
    prev_str = f"{prev_block:0{DIGITS_COUNT - 1}d}"
    curr_str = f"{curr_block:0{DIGITS_COUNT - 1}d}"
    
    depth = 0
    for i in range(DIGITS_COUNT - 2, -1, -1):
        if prev_str[i] == '9' and curr_str[i] == '0':
            depth += 1
        else:
            break
    return depth + 1

def main():
    global start_time
    print(f"=== БРУТФОРС {DIGITS_COUNT}-ЗНАЧНОГО ЗАМКА (ИМПУЛЬСНЫЙ 0-9) ===")
    print("Экстренная остановка: Ctrl + 1")
    print("Старт через 5 секунд...")
    
    for i in range(5, 0, -1):
        print(f"{i}...")
        time.sleep(1)
        
    start_time = time.time()
    print(f"{get_ts()} ПОЕХАЛИ!\n")

    total_blocks = 10**(DIGITS_COUNT - 1) # Всего блоков по 10 цифр (для 6 знаков = 100 000)

    for block in range(START_TEN_BLOCK, total_blocks):
        if not is_running:
            break

        prefix_code = f"{block:0{DIGITS_COUNT - 1}d}"
        print(f"{get_ts()} [БЛОК {block + 1}/{total_blocks}] Диапазон: [{prefix_code}0 ... {prefix_code}9]")

        # 1. ЕДИНСТВЕННОЕ ЗАЖАТИЕ: Прокручивает весь первый разряд от 0 до 9 за 5.13 сек
        hold_key(KEY_INTERACT, FULL_ROTATION_TIME)
        sleep_rnd(*DELAY_BETWEEN_ACTIONS)

        # 2. Перенос разряда (происходит в конце каждого блока 0-9)
        if block < total_blocks - 1:
            curr_block = block + 1
            overflow_depth = calculate_overflow(block, curr_block)

            print(f"  {get_ts()} [ДЕБАГ] Смена блока десятков. Глубина переноса: {overflow_depth}")

            # Переходим фокусом к нужному старшему разряду
            for shift in range(overflow_depth):
                click_key(KEY_INTERACT)
                sleep_rnd(*DELAY_BETWEEN_ACTIONS)

            # Проворачиваем старший разряд на +1 цифру
            hold_key(KEY_INTERACT, ONE_DIGIT_TIME)
            sleep_rnd(*DELAY_BETWEEN_ACTIONS)

            # Возвращаем фокус на 1-й разряд (дощелкиваем кольцо до конца)
            remaining_clicks = DIGITS_COUNT - overflow_depth
            print(f"  {get_ts()} [ДЕБАГ] Возврат фокуса на 1-й разряд ({remaining_clicks} кликов)...")
            for _ in range(remaining_clicks):
                click_key(KEY_INTERACT)
                sleep_rnd(*DELAY_BETWEEN_ACTIONS)

        sleep_rnd(*DELAY_BETWEEN_ACTIONS)

if __name__ == '__main__':
    listener_thread = threading.Thread(target=start_hotkey_listener, daemon=True)
    listener_thread.start()

    try:
        main()
    except KeyboardInterrupt:
        print("\nЗавершено.")
