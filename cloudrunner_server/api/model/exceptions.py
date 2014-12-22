

class QuotaExceeded(Exception):

    def __init__(self, msg=None, model=None):
        super(QuotaExceeded, self).__init__()
        self.msg = msg
        self.model = model
