# The hackable utils lib for TitleBot


import sys
import os
from threading import Thread


def async(func):
    def exec_thread(*args):
        return Thread(group=None, target=func, args=args).start()
    return exec_thread


def restart_program():
    sys.stderr.write("Restarting...\n")
    python = sys.executable
    os.execl(python, python, *sys.argv)


class Signal(object):

    def __init__(self):
        self.__slots = set()

    def connect(self, slot):
        self.__slots.add(slot)

    def emit(self, *args):
        for slot in self.__slots:
            slot(*args)
