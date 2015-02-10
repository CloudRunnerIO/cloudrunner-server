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

from sqlalchemy import (Column, Integer, String, DateTime, Boolean, Text,
                        ForeignKey, UniqueConstraint, Table,
                        event, distinct, select)
from sqlalchemy.sql.expression import func
from sqlalchemy.orm import relationship, backref

from .base import TableBase
from .users import Org

from cloudrunner_server.api.model.exceptions import QuotaExceeded


class Node(TableBase):
    __tablename__ = 'nodes'
    __table_args__ = (
        UniqueConstraint("name", 'org_id', name="name__org_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    joined_at = Column(DateTime, default=func.now())
    approved_at = Column(DateTime)
    meta = Column(Text)
    approved = Column(Boolean)
    enabled = Column(Boolean, default=True)

    org_id = Column(Integer, ForeignKey(Org.id))
    org = relationship(Org, backref=backref('nodes', cascade='delete'))

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

    @staticmethod
    def count(ctx):
        return ctx.db.query(Node).join(Org).filter(
            Org.name == ctx.user.org).count()


def quotas(connection, target):
    allowed = target.org.tier.nodes
    current = connection.scalar(
        select([func.count(distinct(Node.id))]).where(
            Node.org_id == target.org.id).where(Node.enabled == True))  # noqa

    return allowed, current


@event.listens_for(Node, 'before_insert')
def node_before_insert(mapper, connection, target):
    allowed, current = quotas(connection, target)
    if allowed <= current:
        raise QuotaExceeded(msg="Quota exceeded(%d of %d used)" % (
            current, allowed), model="Node")


@event.listens_for(Node, 'before_update')
def node_before_update(mapper, connection, target):
    if not target.enabled:
        return
    allowed, current = quotas(connection, target)
    if allowed < current:
        raise QuotaExceeded(msg="Quota exceeded(%d of %d used)" % (
            current, allowed), model="Node")

node2group_rel = Table('node2group', TableBase.metadata,
                       Column('node_id', Integer, ForeignKey('nodes.id')),
                       Column('group_id', Integer, ForeignKey('nodegroups.id'))
                       )


class NodeGroup(TableBase):
    __tablename__ = 'nodegroups'
    __table_args__ = (
        UniqueConstraint("name", 'org_id', name="name__org_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))

    org_id = Column(Integer, ForeignKey(Org.id))
    org = relationship(Org, backref='servers')

    nodes = relationship(Node, secondary=node2group_rel, backref="groups")

    @staticmethod
    def visible(ctx):
        return ctx.db.query(NodeGroup).join(Org).filter(
            Org.name == ctx.user.org
        )


class NodeTag(TableBase):
    __tablename__ = 'nodetags'

    id = Column(Integer, primary_key=True)
    value = Column(String(255))

    node_id = Column(Integer, ForeignKey(Node.id))
    node = relationship(Node, backref=backref("tags", cascade="delete"))
