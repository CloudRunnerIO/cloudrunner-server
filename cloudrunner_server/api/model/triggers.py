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

import re
from string import letters, digits
from cloudrunner.util import Enum
from sqlalchemy.sql.expression import func
from sqlalchemy import (Column, Boolean, Integer, String, DateTime,
                        ForeignKey, UniqueConstraint,
                        or_)
from sqlalchemy.orm import relationship

from cloudrunner_server.api.util import random_token

from .base import TableBase
from .users import User, Org
from .library import Script

SOURCE_TYPE = Enum('N/A', 'CRON', 'ENV', 'LOG_CONTENT', 'EXTERNAL')
VALID_NAME = re.compile(r"^[\w\-. ]+$")


class Job(TableBase):
    __tablename__ = 'jobs'
    __table_args__ = (
        UniqueConstraint("name", "owner_id", name="name__owner_id"),
    )

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    name = Column(String(256), index=True)
    enabled = Column(Boolean)
    source = Column(Integer)
    arguments = Column(String(1000))
    key = Column(String(32), default=lambda:
                 random_token(length=32,
                              chars=letters + digits))

    private = Column(Boolean, default=False)
    share_url = Column(String(500))

    target_id = Column(Integer, ForeignKey('scripts.id'))
    owner_id = Column(Integer, ForeignKey('users.id'))

    target = relationship(Script)
    owner = relationship(User)

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

    @staticmethod
    def valid_name(name):
        return re.match(VALID_NAME, name)
