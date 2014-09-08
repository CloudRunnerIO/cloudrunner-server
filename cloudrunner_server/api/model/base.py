#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed
#  * without the express permission of CloudRunner.io
#  *******************************************************/

from sqlalchemy import MetaData
from sqlalchemy.orm import class_mapper
from sqlalchemy.ext.declarative import declarative_base


convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(constraint_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)

metadata = MetaData()
Base = declarative_base(metadata=metadata)


def getattr_func(x, y):
    if not x:
        return None
    if isinstance(x, list):
        return [getattr(a, y) for a in x]
    else:
        ret = getattr(x, y)
        if callable(ret):
            ret = ret()

        return ret


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
