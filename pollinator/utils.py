import logging
import os

import timeout_decorator


def system(cmd):
    logging.info(f"OS.SYSTEM: {cmd}")
    return os.system(cmd)


def popen(cmd):
    logging.info(f"OS.POPEN: {cmd}")
    return os.popen(cmd)


@timeout_decorator.timeout(300)
def system_with_timeout(cmd):
    return system(cmd)
