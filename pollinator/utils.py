import logging
import os


def system(cmd):
    logging.info("OS.SYSTEM: ", cmd, "\n")
    return os.system(cmd)


def popen(cmd):
    return os.popen(cmd).read()
