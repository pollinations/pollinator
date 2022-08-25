import logging
import os


def system(cmd):
    logging.info(f"OS.SYSTEM: {cmd}")
    return os.system(cmd)


def popen(cmd):
    logging.info(f"OS.POPEN: {cmd}")
    return os.popen(cmd)
