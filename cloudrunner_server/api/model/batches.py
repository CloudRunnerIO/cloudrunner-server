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

from sqlalchemy import (Column, Integer, String, DateTime, Text,
                        Boolean, ForeignKey, Table)
from sqlalchemy.orm import relationship, backref
from .base import TableBase
from .library import Script
from .users import Org


script2batch_rel = Table('script2batch', TableBase.metadata,
                         Column(
                             'script_id', Integer, ForeignKey('scripts.id')),
                         Column('batch_id', Integer, ForeignKey('batches.id'))
                         )


class Batch(TableBase):
    __tablename__ = 'batches'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime)
    enabled = Column(Boolean, default=True)
    private = Column(Boolean)

    scripts = relationship(Script, secondary=script2batch_rel,
                           backref=backref("batches"))
    conditions = relationship('Condition', backref='batch', uselist=False)

    @staticmethod
    def visible(ctx):
        return ctx.db.query(Batch).join(Script, Org).filter(
            Org.name == ctx.user.org
        )


class Condition(TableBase):
    __tablename__ = 'conditions'

    id = Column(Integer, primary_key=True)
    type = Column(String(50))
    arguments = Column(Text)
    source_id = Column(Integer, ForeignKey(Script.id))
    dest_id = Column(Integer, ForeignKey(Script.id))
    src_version = Column(String(40))
    dst_version = Column(String(40))

    batch_id = Column(Integer, ForeignKey(Batch.id))

    source = relationship(Script, backref='src_conditions',
                          foreign_keys=[source_id])
    destination = relationship(Script, backref='dst_conditions',
                               foreign_keys=[dest_id])
