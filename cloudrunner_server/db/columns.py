__author__ = 'Ivelin Slavov'

class Column(object):

    def __init__(self, col_type, primary_key=False, null=True,
                 autoincrement=False, default=None, **kwargs):
        self.col_type = col_type
        self.kwargs = kwargs
        self.primary_key = primary_key
        self.null = null
        self.autoincrement = autoincrement
        self.default = default

    def __str__(self):
        return self.col_type