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

from sqlalchemy.sql.expression import func
from sqlalchemy import (Column, Integer, String, DateTime, Boolean, Text,
                        ForeignKey, UniqueConstraint,
                        or_)
from sqlalchemy.orm import relationship, backref
from .base import TableBase
from .users import User, Org


class Repository(TableBase):
    __tablename__ = 'repositories'
    __table_args__ = (
        UniqueConstraint("name", 'org_id', name="name__org_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    is_link = Column(Boolean)
    owner_id = Column(Integer, ForeignKey(User.id))
    private = Column(Boolean, default=False)
    org_id = Column(Integer, ForeignKey(Org.id))

    org = relationship(Org)
    owner = relationship(User)

    @staticmethod
    def visible(ctx):
        return ctx.db.query(Repository).join(User, Org).filter(
            Org.name == ctx.user.org,
            or_(Repository.owner_id == ctx.user.id,
                Repository.private != True)  # noqa
        )


class RepositoryCreds(TableBase):
    __tablename__ = 'repository_creds'

    id = Column(Integer, primary_key=True)
    provider = Column(String(500))
    link = Column(String(500))
    auth_user = Column(String(500))
    auth_pass = Column(String(500))
    auth_args = Column(String(500))
    repository_id = Column(Integer, ForeignKey(Repository.id))

    repository = relationship(Repository)


class Folder(TableBase):
    __tablename__ = 'folders'

    __table_args__ = (
        UniqueConstraint("name", "parent_id", name="name__parent_id"),
        UniqueConstraint("full_name", 'repository_id',
                         name="name__repository_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    full_name = Column(String(500))
    parent_id = Column(Integer, ForeignKey('folders.id'))
    repository_id = Column(Integer, ForeignKey(Repository.id))
    owner_id = Column(Integer, ForeignKey(User.id))

    owner = relationship(User)
    parent = relationship('Folder',
                          remote_side=[id],
                          backref=backref('subfolders'))
    scripts = relationship('Script')
    repository = relationship(Repository, backref=backref('folders'))

    @staticmethod
    def visible(ctx, repository, parent=None):
        q = ctx.db.query(Folder).join(
            Repository, User, Org).filter(
                Org.name == ctx.user.org,
                Repository.name == repository,
                or_(Repository.owner_id == ctx.user.id,
                    Repository.private != True)  # noqa
            )
        q = q.join(Folder.parent,
                   aliased=True).filter(Folder.full_name == parent)
        return q

    @staticmethod
    def editable(ctx, repository, folder_path):
        q = ctx.db.query(Folder).join(
            Repository, User, Org).filter(
                Folder.full_name == folder_path,
                Org.name == ctx.user.org,
                Repository.name == repository,
                or_(Repository.owner_id == ctx.user.id,
                    Repository.private != True)  # noqa
            )
        return q


class Script(TableBase):
    __tablename__ = 'scripts'
    __table_args__ = (
        UniqueConstraint("name", "folder_id", name="name__folder_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    folder_id = Column(Integer, ForeignKey(Folder.id))
    created_at = Column(DateTime, default=func.now())
    content = Column(Text)
    mime_type = Column(String(255), default="text/plain")
    owner_id = Column(Integer, ForeignKey(User.id))

    folder = relationship(Folder)
    owner = relationship(User)

    @staticmethod
    def visible(ctx, repository, folder):
        q = ctx.db.query(Script).join(
            Folder, Repository, User, Org).filter(
                Org.name == ctx.user.org,
                Repository.name == repository,
                or_(Repository.owner_id == ctx.user.id,
                    Repository.private != True),  # noqa
                Folder.full_name == folder
            )
        return q

    @staticmethod
    def find(ctx, path):
        repository, _, path = path.partition("/")
        folder, _, script = path.rpartition("/")

        folder = "/" + folder + "/"
        q = Script.visible(ctx, repository, folder).filter(
            Script.name == script)

        return q

    def full_path(self):
        return "%s%s%s" % (self.folder.repository.name,
                           self.folder.full_name,
                           self.name)
