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
                        or_, event, select, distinct, cast)
from sqlalchemy.orm import relationship, backref, aliased
from .base import TableBase
from .users import User, Org

from cloudrunner_server.util.validator import valid_script_name
from cloudrunner_server.api.model.exceptions import QuotaExceeded


class Repository(TableBase):
    __tablename__ = 'repositories'
    __table_args__ = (
        UniqueConstraint('org_id', 'name'),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    type = Column(String(100))
    owner_id = Column(Integer, ForeignKey(User.id))
    private = Column(Boolean, default=False)
    org_id = Column(Integer, ForeignKey(Org.id))
    enabled = Column(Boolean, default=True)

    org = relationship(Org, backref=backref('library_scripts',
                                            cascade="delete"))
    owner = relationship(User)

    @staticmethod
    def visible(ctx):
        return ctx.db.query(Repository).join(User, Org).filter(
            Org.name == ctx.user.org,
            or_(Repository.owner_id == ctx.user.id,
                Repository.private != True)  # noqa
        )

    @staticmethod
    def own(ctx):
        return ctx.db.query(Repository).join(User, Org).filter(
            Org.name == ctx.user.org,
            or_(Repository.owner_id == ctx.user.id)
        )

    def editable(self, ctx):
        return self.owner_id == int(ctx.user.id) and self.enabled and \
            self.type == "cloudrunner"

    def removable(self, ctx):
        return self.owner_id == int(ctx.user.id)

    @staticmethod
    def count(ctx):
        return ctx.db.query(Repository).join(Org).filter(
            Org.name == ctx.user.org).count()


def quotas(connection, target):
    total_allowed = target.org.tier.total_repos

    current_total = connection.scalar(
        select([func.count(distinct(Repository.id))]).where(
            Repository.org_id == target.org.id).where(
                Repository.enabled == True))  # noqa

    return total_allowed, current_total


@event.listens_for(Repository, 'before_insert')
def repo_before_insert(mapper, connection, target):

    total_allowed, current_total = quotas(connection, target)
    if total_allowed <= current_total:
        raise QuotaExceeded(msg="Quota exceeded(%d of %d used)" % (
            current_total, total_allowed), model="Repository")


@event.listens_for(Repository, 'before_update')
def repo_before_update(mapper, connection, target):
    if not target.enabled:
        return
    total_allowed, current_total = quotas(connection, target)
    if total_allowed < current_total:
        raise QuotaExceeded(msg="Quota exceeded(%d of %d used)" % (
            current_total, total_allowed), model="Repository")


class RepositoryCreds(TableBase):
    __tablename__ = 'repository_creds'

    id = Column(Integer, primary_key=True)
    provider = Column(String(500))
    link = Column(String(500))
    auth_user = Column(String(500))
    auth_pass = Column(String(500))
    auth_args = Column(String(500))
    repository_id = Column(Integer, ForeignKey(Repository.id))

    repository = relationship(Repository,
                              backref=backref('credentials',
                                              cascade="delete",
                                              uselist=False))


class Folder(TableBase):
    __tablename__ = 'folders'

    __table_args__ = (
        UniqueConstraint("name", "parent_id"),
        UniqueConstraint("full_name", 'repository_id'),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(500))
    full_name = Column(String(4000))
    parent_id = Column(Integer, ForeignKey('folders.id'))
    repository_id = Column(Integer, ForeignKey(Repository.id))
    created_at = Column(DateTime, default=func.now())
    owner_id = Column(Integer, ForeignKey(User.id))
    etag = Column(String(100))

    owner = relationship(User, backref=backref('library_folders',
                                               cascade="delete"))
    parent = relationship('Folder',
                          remote_side=[id],
                          backref=backref('subfolders', cascade="delete"))
    scripts = relationship('Script')
    repository = relationship(Repository, backref=backref('folders',
                                                          cascade="delete"))

    @staticmethod
    def find(ctx, full_path):
        repository, _, path = full_path.lstrip('/').partition("/")

        path = "/" + path
        q = Folder.visible(ctx, repository).filter(
            Folder.full_name == path)

        return q

    @staticmethod
    def visible(ctx, repository, parent=None):
        q = ctx.db.query(Folder).join(
            Repository, User, Org).filter(
                Org.name == ctx.user.org,
                Repository.name == repository,
                or_(Repository.owner_id == ctx.user.id,
                    Repository.private != True)  # noqa
            )
        if parent:
            parent_tbl = aliased(Folder)
            q = q.join(parent_tbl, parent_tbl.id == Folder.parent_id).filter(
                parent_tbl.full_name == parent)
        return q

    @staticmethod
    def editable(ctx, repository, folder_path):
        q = ctx.db.query(Folder).join(
            Repository, User, Org).filter(
                Folder.full_name == folder_path,
                Org.name == ctx.user.org,
                Repository.name == repository,
                Repository.owner_id == ctx.user.id,
                Repository.enabled == True
            )  # noqa
        return q

    def can_edit(self, ctx,):
        return (self.repository.owner_id == ctx.user.id and
                self.repository.enabled == True
                and self.repository.type == "cloudrunner")  # noqa


class Revision(TableBase):
    __tablename__ = 'revisions'
    __table_args__ = (UniqueConstraint("script_id", "version"), )

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    version = Column(String(20))
    draft = Column(Boolean)
    content = Column(Text)

    script_id = Column(Integer, ForeignKey('scripts.id'))

    script = relationship('Script', backref=backref('history',
                                                    cascade="delete"))


@event.listens_for(Revision, 'before_insert')
def revision_before_insert(mapper, connection, target):
    if target.script_id:
        scr_id = target.script_id
    elif target.script:
        scr_id = target.script.id
    else:
        scr_id = None

    if scr_id and not target.version and not target.draft:
        q = select(
            [func.coalesce(
                select([cast(Revision.version, Integer) + 1], limit=1).
                where(Revision.script_id == scr_id).
                group_by(Revision.id).
             having(Revision.id == func.max(Revision.id)).
             order_by(Revision.id.desc()).
             as_scalar(), 1)])
        target.version = connection.scalar(q)


class Script(TableBase):
    __tablename__ = 'scripts'
    __table_args__ = (
        UniqueConstraint("name", "folder_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    folder_id = Column(Integer, ForeignKey(Folder.id))
    created_at = Column(DateTime, default=func.now())
    mime_type = Column(String(255), default="text/plain")
    allow_sudo = Column(Boolean)
    etag = Column(String(100))

    owner_id = Column(Integer, ForeignKey(User.id))

    folder = relationship(Folder, backref=backref('folder_scripts',
                                                  cascade="delete"))
    owner = relationship(User, backref=backref('library_scripts',
                                               cascade="delete"))

    def contents(self, ctx, rev=None, **kwargs):
        if rev and str(rev).lower() != 'head':
            _rev = ctx.db.query(Revision).filter(
                Revision.script_id == self.id,
                Revision.version == rev).first()
        else:
            _rev = ctx.db.query(Revision).filter(
                Revision.script_id == self.id,
                func.coalesce(Revision.draft, False) != False  # noqa
                ).order_by(Revision.created_at.desc()).first()
        if _rev:
            return _rev
        else:
            return None

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
    def editable(ctx, repository, folder):
        q = ctx.db.query(Script).join(
            Folder, Repository, User, Org).filter(
                Org.name == ctx.user.org,
                Repository.name == repository,
                Repository.owner_id == ctx.user.id,
                Repository.enabled == True,
                Folder.full_name == folder
            )  # noqa
        return q

    @staticmethod
    def find(ctx, full_path):
        repository, _, path = full_path.lstrip('/').partition("/")
        folder, _, script = path.rpartition("/")

        if folder:
            folder = "/" + folder.strip('/') + "/"
        else:
            folder = '/'
        q = Script.visible(ctx, repository, folder).filter(
            Script.name == script)

        return q

    @staticmethod
    def load(ctx, path):
        repository, _, path = path.partition("/")
        folder, _, script = path.rpartition("/")

        if folder == '':
            folder = '/'
        else:
            folder = "/" + folder + "/"
        q = ctx.db.query(Script).join(
            Folder, Repository, Org).filter(
                Org.name == ctx.user.org,
                Repository.name == repository,
                Folder.full_name == folder,
                Script.name == script)
        return q

    def full_path(self):
        return "%s%s%s" % (self.folder.repository.name,
                           self.folder.full_name,
                           self.name)

    @staticmethod
    def valid_name(name):
        return valid_script_name(name)

    @staticmethod
    def parse(full_path):
        path = full_path.lstrip('/')
        repo, _, scr_path = path.partition('/')
        path, _, script = scr_path.rpartition('/')
        if not path:
            path = "/"
        else:
            path = "/%s/" % path
        script, _, rev = script.rpartition('@')
        if not script:
            script = rev
            rev = None

        return repo, path, script, rev
