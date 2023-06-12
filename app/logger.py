import os, logging

class Logger():
    def __init__(self, level):
        os.makedirs("logs/", exist_ok=True)
        logging.basicConfig(filename="logs/log.log", level=level,
                            format='%(asctime)s %(levelname)s : %(message)s')

    def error(self,message):
        logging.error(message)
        #print(message)

    def debug(self,message):
        logging.debug(message)
        #print(message)

    def warn(self,message):
        logging.warning(message)
        #print(message)

    def info(self,message):
        logging.info(message)
        #print(message)

# CRITICAL = 50
# FATAL = CRITICAL
# ERROR = 40
# WARNING = 30
# WARN = WARNING
# INFO = 20
# DEBUG = 10
# NOTSET = 0