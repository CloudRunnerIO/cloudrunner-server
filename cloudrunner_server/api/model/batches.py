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
from sqlalchemy.sql.expression import func
from .base import TableBase
from .library import Script
from .users import Org


class Batch(TableBase):
    __tablename__ = 'batches'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    enabled = Column(Boolean, default=True)
    private = Column(Boolean)

    source_id = Column(Integer, ForeignKey(Script.id))

    source = relationship(Script, backref=backref('batch', uselist=False))

    @staticmethod
    def visible(ctx):
        return ctx.db.query(Batch).join(Script, Org).filter(
            Org.name == ctx.user.org
        )


class ScriptStep(TableBase):
    __tablename__ = 'scriptsteps'

    id = Column(Integer, primary_key=True)
    root = Column(Boolean)
    as_sudo = Column(Boolean)
    version = Column(String(40))

    batch_id = Column(Integer, ForeignKey(Batch.id))
    script_id = Column(Integer, ForeignKey(Script.id))

    batch = relationship(Batch, backref=backref("scripts", cascade="delete"))
    script = relationship(Script, backref=backref('script_steps'))


class Condition(TableBase):
    __tablename__ = 'conditions'

    id = Column(Integer, primary_key=True)
    type = Column(String(50))
    arguments = Column(Text)
    src_id = Column(Integer, ForeignKey(ScriptStep.id))
    dst_id = Column(Integer, ForeignKey(ScriptStep.id))

    batch_id = Column(Integer, ForeignKey(Batch.id))

    source = relationship(ScriptStep, backref='src_conditions',
                          foreign_keys=[src_id])
    destination = relationship(ScriptStep, backref='dst_conditions',
                               foreign_keys=[dst_id])
    batch = relationship(Batch, backref=backref('conditions',
                                                cascade="delete"))
