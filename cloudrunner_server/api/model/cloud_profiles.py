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
                        ForeignKey, UniqueConstraint, func)
from sqlalchemy.orm import relationship, backref


from .base import TableBase
from .nodes import Node
from .users import User


class CloudProfile(TableBase):
    __tablename__ = 'cloud_profiles'
    __table_args__ = (
        UniqueConstraint("name", 'owner_id'),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    type = Column(String(25))
    username = Column(Text)
    password = Column(Text)
    arguments = Column(Text)
    created_at = Column(DateTime, default=func.now())
    clear_nodes = Column(Boolean, default=True)
    owner_id = Column(Integer, ForeignKey(User.id))
    owner = relationship(User, backref=backref('cloud_profiles',
                                               cascade='delete'))

    @staticmethod
    def my(ctx):
        return ctx.db.query(CloudProfile).filter(
            CloudProfile.owner_id == ctx.user.id
        )


class CloudShare(TableBase):

    __tablename__ = 'cloud_profiles_shares'
    __table_args__ = (
        UniqueConstraint("name", 'password'),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    password = Column(String(4000))
    created_at = Column(DateTime, default=func.now())
    node_quota = Column(Integer)

    profile_id = Column(Integer, ForeignKey(CloudProfile.id))
    profile = relationship(CloudProfile, backref=backref('shares',
                                                         cascade='delete'))

    @staticmethod
    def my(ctx, profile):
        return ctx.db.query(CloudShare).join(CloudProfile).filter(
            CloudProfile.owner_id == ctx.user.id, CloudProfile.name == profile
        )


class AttachedProfile(TableBase):

    __tablename__ = 'cloud_attached_profiles'
    __table_args__ = (
        UniqueConstraint("owner_id", 'share_id'),
    )

    id = Column(Integer, primary_key=True)

    owner_id = Column(Integer, ForeignKey(User.id))
    owner = relationship(User, backref=backref('profile_attachments',
                                               cascade='delete'))
    share_id = Column(Integer, ForeignKey(CloudShare.id))
    share = relationship(CloudShare, backref=backref('attachments',
                                                     cascade='delete'))

    @staticmethod
    def my(ctx):
        return ctx.db.query(AttachedProfile).filter(
            AttachedProfile.owner_id == ctx.user.id
        )


class SharedNode(TableBase):

    __tablename__ = 'node_shares'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())

    share_id = Column(Integer, ForeignKey(CloudShare.id))
    share = relationship(CloudShare, backref=backref('shared_nodes',
                                                     cascade='delete'))
    node_id = Column(Integer, ForeignKey(Node.id))
    node = relationship(Node, backref=backref('shares', cascade='delete'),
                        cascade='delete')
