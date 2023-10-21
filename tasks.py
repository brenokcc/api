import traceback
import time
import datetime
from threading import Thread
from django.core.cache import cache
from uuid import uuid1


class Task(Thread):

    def __init__(self, *args, **kwargs):
        self.key = uuid1().hex
        super().__init__(*args, **kwargs)

    def iterate(self, iterable):
        total = len(iterable)
        for i, obj in enumerate(iterable):
            progress = int(i / total * 100)
            cache.set(self.key, progress, timeout=10)
            yield obj
        cache.set(self.key, 100)

class TestTask(Task):

    def run(self):
        for i in self.iterate(range(1, 11)):
            time.sleep(1)
