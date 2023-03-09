import random
import time as t

import pyautogui as py


def rnd_sleep(x, y):
    sleep = random.uniform(x, y)
    t.sleep(sleep)
    print(f'Задержка: {sleep}')


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

    print(f'Прокрутка 1 цифры заняла {one_rotation}')


def func_ten():
    i = 0
    while i < 10:
        func_full_rotation()
        rnd_sleep(0.1, 0.3)
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        func_one_rotation()
        py.press('f')
        i = i + 1
        print(i)


def one_hundred():
    i = 0
    while i < 10:
        rnd_sleep(0.1, 0.3)
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        func_one_rotation()
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        i = i + 1
        print(i * 100)
        func_ten()


def one_thousand():
    i = 0
    while i < 10:
        rnd_sleep(0.1, 0.3)
        py.press('f')
        rnd_sleep(0.1, 0.3)
        func_one_rotation()
        rnd_sleep(0.1, 0.3)
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        rnd_sleep(0.1, 0.3)
        py.press('f')
        func_ten()
        one_hundred()
        i = i + 1
        print(i * 1000)


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
