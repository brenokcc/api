

class JsonResponseReadyException(Exception):

    def __init__(self, data, *args, **kwargs):
        self.data = data
        super().__init__(*args, **kwargs)