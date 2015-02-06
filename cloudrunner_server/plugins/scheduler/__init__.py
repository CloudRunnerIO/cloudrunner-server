import re

TOKEN_SPLIT = re.compile(r'\s+')
RANGE = re.compile(",")
EACH = re.compile("/")


class Period(object):

    class Token(object):

        def __init__(self, token):
            self.any = token == "*"
            self.interval = token
            if self.interval.isdigit():
                self.int = int(self.interval)
            else:
                self.int = -1

    def __init__(self, token):
        self.raw_tokens = TOKEN_SPLIT.split(token)
        self.tokens = [self.Token(t) for t in self.raw_tokens]

    def is_valid(self):
        try:
            if len(filter(None, [t for t in self.raw_tokens])) != 5:
                return False

            if not self.minutes.any:
                ranges, each = (self._range(self.minutes),
                                self._each(self.minutes))
                if ranges and [r for r in ranges if r < 0 or r > 59]:
                    return False
                if each and (each < 0 or each > 59):
                    return False
                if not ranges and not each and (self.minutes.int < 0
                                                or self.minutes.int > 59):
                    return False

            if not self.hours.any:
                ranges, each = self._range(self.hours), self._each(self.hours)
                if ranges and [r for r in ranges if r < 0 or r > 23]:
                    return False
                if each and (each < 0 or each > 23):
                    return False
                if not ranges and not each and (self.hours.int < 0
                                                or self.hours.int > 23):
                    return False

            if not self.day.any:
                ranges, each = self._range(self.day), self._each(self.day)
                if ranges and [r for r in ranges if r < 1 or r > 31]:
                    return False
                if each and (each < 1 or each > 31):
                    return False
                if not ranges and not each and (self.day.int < 1
                                                or self.day.int > 31):
                    return False

            if not self.month.any:
                ranges, each = self._range(self.month), self._each(self.month)
                if ranges and [r for r in ranges if r < 1 or r > 12]:
                    return False
                if each and (each < 1 or each > 12):
                    return False
                if not ranges and not each and (self.month.int < 1
                                                or self.month.int > 12):
                    return False

            if not self.dow.any:
                ranges, each = self._range(self.dow), self._each(self.dow)
                if ranges and [r for r in ranges if r < 0 or r > 6]:
                    return False
                if each and (each < 0 or each > 6):
                    return False
                if not ranges and not each and (self.dow.int < 0
                                                or self.dow.int > 6):
                    return False

            return True
        except ValueError:
            return False

    def is_only_minutes(self):
        return filter(lambda t: t.any, self.tokens[1:])

    @property
    def total_minutes(self):
        inter = self.minutes.interval
        if inter.isdigit():
            return int(inter)
        ranges = self._range(self.minutes)
        each = self._each(self.minutes)
        if ranges:
            _min = 60
            prev = ranges[0]
            for _r in ranges[1:]:
                diff = _r - prev
                _min = min(diff, _min)
                prev = _r
            return _min
        elif each:
            return each
        else:
            return 0

    @property
    def minutes(self):
        return self.tokens[0]

    @property
    def hours(self):
        return self.tokens[1]

    @property
    def day(self):
        return self.tokens[2]

    @property
    def month(self):
        return self.tokens[3]

    @property
    def dow(self):
        return self.tokens[4]

    def _range(self, token):
        ranges = RANGE.split(token.interval)
        if len(ranges) > 1:
            return sorted([int(r) for r in ranges])

    def _each(self, token):
        each = EACH.split(token.interval)
        if len(each) == 2:
            return int(each[1])

    def __str__(self):
        return " ".join([t.interval for t in self.tokens])

    def values(self):
        return [t.interval for t in self.tokens]

    @property
    def _(self):
        return str(self)
