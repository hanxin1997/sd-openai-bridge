import logging
import sys
from datetime import datetime
from collections import deque

log_buffer = deque(maxlen=2000)


class BufferHandler(logging.Handler):
    def emit(self, record):
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "message": self.format(record)
        }
        log_buffer.append(log_entry)


def setup_logger():
    log = logging.getLogger("sd-openai-bridge")
    log.setLevel(logging.DEBUG)
    
    if not log.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_format = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(console_format)
        
        buffer_handler = BufferHandler()
        buffer_handler.setLevel(logging.DEBUG)
        buffer_handler.setFormatter(logging.Formatter('%(message)s'))
        
        log.addHandler(console_handler)
        log.addHandler(buffer_handler)
    
    return log


logger = setup_logger()


def get_logs():
    return list(log_buffer)


def clear_logs():
    log_buffer.clear()