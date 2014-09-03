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

from sqlalchemy import (Column, Integer, String, DateTime, Boolean,
                        ForeignKey, UniqueConstraint)
from sqlalchemy.orm import relationship
from .base import TableBase
from .users import Org


class Node(TableBase):
    __tablename__ = 'nodes'
    __table_args__ = (
        UniqueConstraint("name", 'org_id', name="name__org_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    joined_at = Column(DateTime)
    approved_at = Column(DateTime)
    key_file = Column(String(512), unique=True)
    cert_file = Column(String(512), unique=True)
    csr_subject = Column(String(512))
    approved = Column(Boolean)

    org_id = Column(Integer, ForeignKey(Org.id))
    org = relationship(Org, backref='nodes')

    @staticmethod
    def visible(ctx):
        return ctx.db.query(Node).join(Org).filter(
            Org.name == ctx.user.org
        )

    @staticmethod
    def pending(ctx):
        return Node.visible(ctx).filter(Node.approved != True)  # noqa

    @staticmethod
    def signed(ctx):
        return Node.visible(ctx).filter(Node.approved == True)  # noqa
