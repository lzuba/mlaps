import os, logging, collections
from logging.handlers import RotatingFileHandler
from typing import Union


class Logger():
    def __init__(self, level: Union[int, str], logLocation: str, numberOfLinesToRetain: int):
        os.makedirs(logLocation, exist_ok=True)

        self.tail = TailLogger(numberOfLinesToRetain)
        formatter = logging.Formatter('%(asctime)s - %(name)s@%(funcName)s - %(levelname)s - %(message)s')

        log_handler = self.tail.log_handler
        log_handler.setFormatter(formatter)
        logFile_handler = RotatingFileHandler(f"{logLocation.rstrip(os.sep)}/mlaps.log", encoding='utf8',maxBytes=100000, backupCount=1)
        logFile_handler.setFormatter(formatter)

        rootLogger = logging.getLogger()
        rootLogger.addHandler(log_handler)
        rootLogger.addHandler(logFile_handler)
        rootLogger.setLevel(int(level) if str.isnumeric(level) else level)


#https://stackoverflow.com/a/37967421
class TailLogHandler(logging.Handler):

    def __init__(self, log_queue):
        logging.Handler.__init__(self)
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.append(self.format(record))


class TailLogger(object):

    def __init__(self, maxlen):
        self._log_queue = collections.deque(maxlen=maxlen)
        self._log_handler = TailLogHandler(self._log_queue)

    def contents(self):
        return '\n'.join(self._log_queue)

    @property
    def log_handler(self):
        return self._log_handler


# CRITICAL = 50
# FATAL = CRITICAL
# ERROR = 40
# WARNING = 30
# WARN = WARNING
# INFO = 20
# DEBUG = 10
# NOTSET = 0