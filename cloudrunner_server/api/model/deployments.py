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

from sqlalchemy import (Column, Integer, String, DateTime, Text, Boolean,
                        Enum, ForeignKey, UniqueConstraint, func,
                        event, select, distinct, join)
from sqlalchemy.orm import relationship, backref

from cloudrunner_server.api.model.exceptions import QuotaExceeded

from .base import TableBase
from .cloud_profiles import CloudProfile
from .users import User, Org


class Deployment(TableBase):
    __tablename__ = 'deployments'
    __table_args__ = (
        UniqueConstraint("name", 'owner_id'),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    content = Column(Text)
    created_at = Column(DateTime, default=func.now())
    enabled = Column(Boolean, default=True)
    status = Column(Enum('Pending',
                         'Starting', 'Running',
                         'Rebuilding',
                         'Patching',
                         'Stopping', 'Stopped',
                         'Deleting',
                         name="status"))
    owner_id = Column(Integer, ForeignKey(User.id))
    owner = relationship(User, backref=backref('deployments',
                                               cascade='delete'))

    @staticmethod
    def my(ctx):
        return ctx.db.query(Deployment).filter(
            Deployment.owner_id == ctx.user.id
        )

    @staticmethod
    def count(ctx):
        return ctx.db.query(Deployment).join(User, Org).filter(
            Org.name == ctx.user.org).count()


def quotas(connection, target):
    org = target.owner.org
    total_allowed = org.tier.deployments

    current_total = connection.scalar(
        select([func.count(distinct(Deployment.id))]).select_from(
            join(Deployment, User)).where(
            User.org_id == org.id).where(
                Deployment.enabled == True))  # noqa

    return total_allowed, current_total


@event.listens_for(Deployment, 'before_insert')
def depl_before_insert(mapper, connection, target):
    total_allowed, current_total = quotas(connection, target)
    if total_allowed <= current_total:
        raise QuotaExceeded(msg="Quota exceeded(%d of %d used)" % (
            current_total, total_allowed), model="Deployment")


@event.listens_for(Deployment, 'before_update')
def depl_before_update(mapper, connection, target):
    if not target.enabled:
        return
    total_allowed, current_total = quotas(connection, target)
    if total_allowed < current_total:
        raise QuotaExceeded(msg="Quota exceeded(%d of %d used)" % (
            current_total, total_allowed), model="Deployment")


class Resource(TableBase):
    __tablename__ = 'depl_resources'
    __table_args__ = (
        UniqueConstraint('server_id', 'profile_id'),
    )

    id = Column(Integer, primary_key=True)
    server_name = Column(String(255))
    server_id = Column(String(255))
    meta = Column(Text)
    created_at = Column(DateTime, default=func.now())

    deployment_id = Column(Integer, ForeignKey(Deployment.id))
    deployment = relationship(Deployment,
                              backref=backref('resources', cascade='delete'))
    profile_id = Column(Integer, ForeignKey(CloudProfile.id))
    profile = relationship(CloudProfile,
                           backref=backref('resources', cascade='delete'))
