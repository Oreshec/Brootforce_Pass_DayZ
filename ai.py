import random
import time as t
import sys
import keyboard as kb


def emergency_exit():
    print("Аварийное завершение программы!")
    sys.exit()


kb.add_hotkey('ctrl+shift+q', emergency_exit)


def rnd_sleep(x, y):
    sleep = random.uniform(x, y)
    print(f'Задержка: {sleep}')
    t.sleep(sleep)


def press_and_release_f():
    kb.press_and_release('f')
    rnd_sleep(0.1, 0.3)


def func_full_rotation():
    kb.press('f')
    rnd_sleep(5.10, 5.15)
    kb.release('f')


def func_one_rotation():
    kb.press('f')
    rnd_sleep(5.10 / 10, 5.15 / 10)
    kb.release('f')


def perform_rotations(rotation_count):
    for _ in range(rotation_count):
        func_full_rotation()
        for _ in range(3):
            press_and_release_f()
        func_one_rotation()
        press_and_release_f()
        print(rotation_count)


def main_rotations(rotation_set, multiplier):
    for i in range(10):
        rnd_sleep(0.1, 0.3)
        press_and_release_f()
        func_one_rotation()
        for _ in range(3):
            press_and_release_f()
        perform_rotations(rotation_set)
        print((i + 1) * multiplier)


def timer():
    for z in range(1, 6):
        t.sleep(1)
        print(z)
        if z == 5:
            print('start!')


def main():
    for i in range(10):
        perform_rotations(10)
        main_rotations(10, 100)
        main_rotations(10, 1000)


if __name__ == "__main__":
    t.sleep(3)
    print("Программа работает. Нажмите Ctrl+Shift+Q для аварийного завершения.")
    main()
