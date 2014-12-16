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

from datetime import datetime, timedelta
from sqlalchemy.sql.expression import func
from sqlalchemy import (
    Table, Column, Boolean, Integer, String, Text, DateTime,
    ForeignKey, UniqueConstraint, Enum, event, select, distinct)
from sqlalchemy.orm import relationship, backref
import uuid

from .base import TableBase

from cloudrunner.util.crypto import hash_token
from cloudrunner_server.api.util import random_token
from cloudrunner_server.api.model.base import QuotaExceeded

TOKEN_LENGTH = 64


class Org(TableBase):
    __tablename__ = 'organizations'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    uid = Column(String(100), unique=True,
                 default=lambda ctx: uuid.uuid4().hex)
    name = Column(String(100), unique=True)
    cert_ca = Column(Text)
    cert_key = Column(Text)
    active = Column(Boolean)
    tier_id = Column(Integer, ForeignKey('usagetiers.id'), nullable=False)

    tier = relationship('UsageTier', backref=backref('orgs'))


class User(TableBase):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    username = Column(String(100), unique=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(100), unique=True)
    position = Column(String(100))
    department = Column(String(100))
    password = Column(String(128))
    active = Column(Boolean, default=True)

    org_id = Column(Integer, ForeignKey('organizations.id'))

    org = relationship('Org')
    permissions = relationship('Permission')
    roles = relationship('Role')
    tokens = relationship('Token', backref='user')

    def set_password(self, password):
        self.password = hash_token(password)

    @staticmethod
    def visible(ctx):
        return ctx.db.query(User).join(Org).filter(
            User.active == True,  # noqa
            Org.name == ctx.user.org
        )

    @staticmethod
    def current(ctx):
        return ctx.db.query(User).join(Org).filter(
            Org.name == ctx.user.org,
            User.id == ctx.user.id
        )

    @staticmethod
    def create_token(ctx, user_id, days=None, minutes=None, scope=None):
        if days:
            expiry = datetime.now() + timedelta(days=days)
        elif minutes:
            expiry = datetime.now() + timedelta(minutes=minutes)
        else:
            expiry = datetime.now() + timedelta(minutes=30)
        token = Token(user_id=user_id,
                      expires_at=expiry,
                      scope=scope,
                      value=random_token())
        ctx.db.add(token)
        ctx.db.commit()
        return token


@event.listens_for(User, 'before_insert')
def user_before_insert(mapper, connection, target):
    allowed = target.org.tier.users
    current = connection.scalar(
        select([func.count(distinct(User.id))]).where(
            User.org_id == target.org.id))
    if allowed <= current:
        raise QuotaExceeded(msg="Quota exceeded(%d of %d used)" % (
            current, allowed), model="User")


class Permission(TableBase):
    __tablename__ = 'permissions'
    __table_args__ = (
        UniqueConstraint("name", 'user_id', name="name__user_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User')


class Role(TableBase):
    __tablename__ = 'roles'
    __table_args__ = (
        UniqueConstraint('user_id', "as_user", 'servers',
                         name="user_id__as_user__servers"),
        UniqueConstraint('group_id', "as_user", 'servers',
                         name="group_id__as_user__servers"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    servers = Column(String(100))
    as_user = Column(String(100))
    group_id = Column(Integer, ForeignKey('groups.id'))
    group = relationship('Group', backref='roles')
    user = relationship('User')


user2group_rel = Table('user2group', TableBase.metadata,
                       Column('user_id', Integer, ForeignKey('users.id')),
                       Column('group_id', Integer, ForeignKey('groups.id'))
                       )


class Group(TableBase):
    __tablename__ = 'groups'
    __table_args__ = (
        UniqueConstraint("name", 'org_id', name="name__org_id"),
    )

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey('organizations.id'))
    name = Column(String(100))

    org = relationship('Org')
    users = relationship('User', secondary=user2group_rel, backref="groups")

    @staticmethod
    def visible(ctx):
        return ctx.db.query(Group).join(Org).filter(
            Org.name == ctx.user.org
        )


@event.listens_for(Group, 'before_insert')
def group_before_insert(mapper, connection, target):
    allowed = target.org.tier.groups
    current = connection.scalar(
        select([func.count(distinct(Group.id))]).where(
            Group.org_id == target.org.id))
    if allowed <= current:
        raise QuotaExceeded(msg="Quota exceeded(%d of %d used)" % (
            current, allowed), model="Group")


class Token(TableBase):
    __tablename__ = 'tokens'
    __table_args__ = (
        UniqueConstraint('user_id', 'value', name="user_id__value"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    expires_at = Column(DateTime)
    value = Column(String(TOKEN_LENGTH), default=random_token)
    scope = Column(Enum('LOGIN', 'TRIGGER', 'EXECUTE', 'RECOVER'))


class ApiKey(TableBase):
    __tablename__ = 'apikeys'

    id = Column(Integer, primary_key=True)
    value = Column(String(100), unique=True,
                   default=lambda ctx: uuid.uuid4().hex)

    user_id = Column(Integer, ForeignKey('users.id'))

    user = relationship('User', backref="apikeys")


class UsageTier(TableBase):
    __tablename__ = 'usagetiers'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    title = Column(String(100))
    description = Column(Text)
    total_repos = Column(Integer)
    user_repos = Column(Integer)
    external_repos = Column(Boolean)
    nodes = Column(Integer)
    users = Column(Integer)
    groups = Column(Integer)
    roles = Column(Integer)
    max_timeout = Column(Integer)
    max_concurrent_tasks = Column(Integer)
    log_retention_days = Column(Integer)
    cron_jobs = Column(Integer)
