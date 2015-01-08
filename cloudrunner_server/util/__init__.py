from datetime import datetime
import time


def timestamp():
    return int(time.mktime(time.gmtime()))

MAX_TS = time.mktime(datetime.max.timetuple())
