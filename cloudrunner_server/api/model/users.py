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
    ForeignKey, UniqueConstraint, Enum)
from sqlalchemy.orm import relationship
import uuid

from .base import TableBase

from cloudrunner.util.crypto import hash_token
from cloudrunner_server.api.util import random_token

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


class User(TableBase):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    username = Column(String(100), unique=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(100))
    position = Column(String(100))
    department = Column(String(100))
    password = Column(String(128))

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


class Permission(TableBase):
    __tablename__ = 'permissions'
    __table_args__ = (
        UniqueConstraint("name", 'user_id', name="name__user_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    user_id = Column(Integer, ForeignKey('users.id'))


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


class Token(TableBase):
    __tablename__ = 'tokens'
    __table_args__ = (
        UniqueConstraint('user_id', 'value', name="user_id__value"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    expires_at = Column(DateTime)
    value = Column(String(TOKEN_LENGTH), default=random_token)
    scope = Column(Enum('LOGIN', 'TRIGGER', 'EXECUTE'))
