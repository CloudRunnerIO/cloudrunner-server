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

import uuid
from sqlalchemy.sql.expression import func
from sqlalchemy import (Column, Boolean, Integer, String, DateTime, Text,
                        ForeignKey, UniqueConstraint,
                        or_)
from sqlalchemy.orm import relationship, backref

from .base import TableBase
from .users import User, Org
from .library import Revision


class Job(TableBase):
    __tablename__ = 'cronjobs'
    __table_args__ = (
        UniqueConstraint("name", "owner_id", name="name__owner_id"),
    )

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    name = Column(String(256), index=True)
    enabled = Column(Boolean)
    private = Column(Boolean, default=False)
    exec_period = Column(String(100))
    params = Column(Text)
    uid = Column(String(40), unique=True,
                 default=lambda ctx: uuid.uuid4().hex)

    revision_id = Column(Integer, ForeignKey('revisions.id'))
    owner_id = Column(Integer, ForeignKey('users.id'))

    script = relationship(Revision, backref=backref("jobs"))
    owner = relationship(User, backref=backref("jobs"))

    @staticmethod
    def visible(ctx):
        return ctx.db.query(Job).join(User, Org).filter(
            Org.name == ctx.user.org,
            or_(Job.owner_id == ctx.user.id,
                Job.private != True)  # noqa
        )

    @staticmethod
    def active(ctx):
        return ctx.db.query(Job).join(User).filter(
            Job.enabled == True,
            or_(Job.owner_id == ctx.user.id,
                Job.private != True)  # noqa
        )

    @staticmethod
    def own(ctx):
        return ctx.db.query(Job).join(User).filter(
            Job.owner_id == ctx.user.id
        )
