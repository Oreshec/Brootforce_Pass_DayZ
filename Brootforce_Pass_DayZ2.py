import random
import time as t
import keyboard as kb
import os
import signal
import multiprocessing


def hook(pid):
    while True:
        if kb.is_pressed('ctrl + 1'):
            os.kill(pid, signal.SIGTERM)
            os._exit(1)


def rnd_sleep(x, y):
    sleep = random.uniform(x, y)
    print(f'Задержка: {sleep}')
    t.sleep(sleep)


# крутит число
def func_full_rotation():
    kb.press('f')
    rnd_sleep(5.10, 5.15)  # полная прокрутка / В ходе 1 испытания было получено число 5.13
    kb.release('f')


def func_one_rotation():
    kb.press('f')
    rnd_sleep(5.10 / 10, 5.15 / 10)
    kb.release('f')


def func_ten():
    i = 0
    while i < 10:
        func_full_rotation()
        rnd_sleep(0.1, 0.3)
        kb.press_and_release('f')
        rnd_sleep(0.1, 0.3)
        kb.press_and_release('f')
        rnd_sleep(0.1, 0.3)
        kb.press_and_release('f')
        func_one_rotation()
        kb.press_and_release('f')
        i = i + 1
        print(i)


def one_hundred():
    i = 0
    while i < 10:
        rnd_sleep(0.1, 0.3)
        kb.press_and_release('f')
        rnd_sleep(0.1, 0.3)
        kb.press_and_release('f')
        func_one_rotation()
        kb.press_and_release('f')
        rnd_sleep(0.1, 0.3)
        kb.press_and_release('f')
        i = i + 1
        print(i * 100)
        func_ten()


def one_thousand():
    i = 0
    while i < 10:
        rnd_sleep(0.1, 0.3)
        kb.press_and_release('f')
        rnd_sleep(0.1, 0.3)
        func_one_rotation()
        rnd_sleep(0.1, 0.3)
        kb.press_and_release('f')
        rnd_sleep(0.1, 0.3)
        kb.press_and_release('f')
        rnd_sleep(0.1, 0.3)
        kb.press_and_release('f')
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
    for i in range(10):
        func_ten()
        one_hundred()
        one_thousand()


if __name__ == '__main__':
    timer()
    pid = os.getpid()
    while True:
        multiprocessing.Process(target=hook, args=[pid]).start()
        multiprocessing.Process(target=main).start()
