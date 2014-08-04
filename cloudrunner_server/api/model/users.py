from sqlalchemy.sql.expression import func
from sqlalchemy import (Column, Boolean, Integer, String,
                        DateTime, ForeignKey, Text)
from sqlalchemy.orm import relationship
import uuid

from .base import TableBase
from cloudrunner_server.api.util import random_token

TOKEN_LENGTH = 64


class Org(TableBase):
    __tablename__ = 'organizations'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    uid = Column(String(100), default=lambda ctx: uuid.uuid4().hex)
    name = Column(String(100), unique=True)
    cert_ca = Column(Text)
    cert_key = Column(Text)
    active = Column(Boolean)


class User(TableBase):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    username = Column(String(100), unique=True)
    email = Column(String(100))
    password = Column(String(128))

    org_id = Column(Integer, ForeignKey('organizations.id'))

    org = relationship('Org')
    rights = relationship('Right')
    roles = relationship('Role')
    tokens = relationship('Token')


class Right(TableBase):
    __tablename__ = 'rights'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    user_id = Column(Integer, ForeignKey('users.id'))


class Role(TableBase):
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    user_id = Column(Integer, ForeignKey('users.id'))
    servers = Column(String(100))
    as_user = Column(String(100))


class Token(TableBase):
    __tablename__ = 'tokens'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    expires_at = Column(DateTime)
    value = Column(String(TOKEN_LENGTH), default=random_token)
