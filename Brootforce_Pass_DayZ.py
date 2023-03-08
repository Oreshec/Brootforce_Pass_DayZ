import random
import time as t

import pyautogui as py


def rnd_sleep(x, y):
    random.uniform(x, y)


# крутит число
def func_full_rotation():
    rotation_full = random.uniform(5.10, 5.15)  # полная прокрутка / В ходе 1 испытания было получено число 5.13

    py.keyDown('f')
    t.sleep(rotation_full)
    py.keyUp('f')

    print(f'Полная прокрутка заняла: {rotation_full}')


def func_one_rotation():
    one_rotation = random.uniform(5.10, 5.15)
    one_rotation = one_rotation / 10

    py.keyDown('f')
    t.sleep(one_rotation)
    py.keyUp('f')

    print(f'Одна прокрутка заняла {one_rotation}')


def one_hundred():
    i = 0
    while i < 10:
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        func_one_rotation()
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        i = i + 1
        print(f'Внутри def {i * 100}')
        func_ten()


def one_thousand():
    i = 0
    while i < 10:
        py.press('f')
        func_one_rotation()
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        i = i + 1
        print(f'Внутри def{i * 1000}')


def func_ten():
    i = 0
    while i < 10:
        func_full_rotation()
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        func_one_rotation()
        py.press('f')
        i = i + 1
        print(f'Внутри def {i}')


def calc():
    x = 0
    for n in range(0, 1000):
        x = x + 10
        print(x)


def timer():
    z = 0
    while z < 5:
        t.sleep(1)
        z = z + 1
        print(z)
        if z == 5:
            print('start!')


def main():
    func_ten()
    one_hundred()
    one_thousand()


if __name__ == "__main__":
    timer()
    main()
