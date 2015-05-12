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
                        Enum, ForeignKey, UniqueConstraint, func)
from sqlalchemy.orm import relationship, backref


from .base import TableBase
from .users import User


class Deployment(TableBase):
    __tablename__ = 'deployments'
    __table_args__ = (
        UniqueConstraint("name", 'owner_id'),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    content = Column(Text)
    created_at = Column(DateTime, default=func.now())
    status = Column(Enum('Pending', 'Started', 'Rebuilding', 'Patching',
                         'Stopped', 'Deleting', name="status"))
    owner_id = Column(Integer, ForeignKey(User.id))
    owner = relationship(User, backref=backref('deployments',
                                               cascade='delete'))

    @staticmethod
    def my(ctx):
        return ctx.db.query(Deployment).filter(
            Deployment.owner_id == ctx.user.id
        )
