from sqlalchemy import MetaData
from sqlalchemy.orm import class_mapper
from sqlalchemy.ext.declarative import declarative_base

metadata = MetaData()
Base = declarative_base(metadata=metadata)


def getattr_func(x, y):
    if isinstance(x, list):
        return [getattr(a, y) for a in x]
    else:
        return getattr(x, y)


class TableBase(Base):
    __abstract__ = True

    def serialize(self, skip=[], rel=[]):
        columns = [c.key for c in class_mapper(self.__class__).columns]
        d = dict((c, getattr(self, c)) for c in columns if c not in skip)
        for r in rel:
            c, k = r[:2]
            modifier = None
            if len(r) > 2:
                modifier = r[2]
            v = reduce(getattr_func, c.split("."), self)
            if modifier:
                d[k] = modifier(v)
            else:
                d[k] = v
        return d
