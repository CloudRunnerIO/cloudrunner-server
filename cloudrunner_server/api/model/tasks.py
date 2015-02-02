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

from sqlalchemy import (Column, String, Integer, DateTime, ForeignKey, Text,
                        distinct)
from sqlalchemy.orm import relationship, backref, joinedload
from sqlalchemy.sql.expression import func
import uuid

from .base import TableBase
from .users import User, Org
from .library import Revision, Script, Folder

from cloudrunner.util import Enum

LOG_STATUS = Enum('Unknown', 'Running', 'Finished')


class TaskGroup(TableBase):
    __tablename__ = 'taskgroups'

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey('batches.id'))

    batch = relationship('Batch')

    @staticmethod
    def unique(ctx):
        return ctx.db.query(distinct(TaskGroup.id)).join(
            Task, Run, User, Org).outerjoin(RunNode).filter(
                Org.name == ctx.user.org)

    @staticmethod
    def visible(ctx):
        return ctx.db.query(TaskGroup).join(
            Task, User, Org).filter(Org.name == ctx.user.org)


class Task(TableBase):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True)
    uuid = Column(String(40), index=True, unique=True,
                  default=lambda ctx: uuid.uuid4().hex)
    created_at = Column(DateTime, default=func.now())
    status = Column(Integer)
    timeout = Column(Integer)

    exec_start = Column(Integer)
    exec_end = Column(Integer)
    exit_code = Column(Integer)

    owner_id = Column(Integer, ForeignKey('users.id'))
    taskgroup_id = Column(Integer, ForeignKey(TaskGroup.id))
    parent_id = Column(Integer, ForeignKey('tasks.id'))
    revision_id = Column(Integer, ForeignKey('revisions.id'))

    owner = relationship('User', backref=backref('tasks', cascade="delete"))
    script_content = relationship(Revision,
                                  backref=backref('tasks', cascade="delete"))
    group = relationship(TaskGroup, backref=backref('tasks'))
    parent = relationship('Task',
                          remote_side=[id],
                          backref=backref('children'))

    @staticmethod
    def visible(ctx, simple=False):
        if simple:
            return ctx.db.query(Task).join(
                User, Org).options(
                    joinedload(Task.script_content)).filter(
                        Org.name == ctx.user.org)
        else:
            return ctx.db.query(Task).join(
                User, Org).options(
                    joinedload(Task.script_content).
                    joinedload(Revision.script).
                    joinedload(Script.folder).
                    joinedload(Folder.repository)).filter(
                        Org.name == ctx.user.org)

    def is_visible(self, request):
        if self.owner_id == int(request.user.id):
            return True

        if not self.script_content.script:
            return False

        return not self.script_content.script.folder.repository.private


class Run(TableBase):
    __tablename__ = 'runs'

    id = Column(Integer, primary_key=True)
    uuid = Column(String(40), index=True, unique=True)
    lang = Column(String(100))
    env_in = Column(Text)
    env_out = Column(Text)
    timeout = Column(Integer)
    exit_code = Column(Integer)
    target = Column(Text)
    full_script = Column(Text)
    exec_start = Column(Integer)
    exec_end = Column(Integer)
    step_index = Column(Integer)

    task_id = Column(Integer, ForeignKey('tasks.id'))
    exec_user_id = Column(Integer, ForeignKey('users.id'))

    task = relationship('Task', backref=backref('runs'))
    exec_user = relationship('User', backref=backref('runs'))


class RunNode(TableBase):
    __tablename__ = 'run_nodes'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    exit_code = Column(Integer)
    as_user = Column(String(200))

    run_id = Column(Integer, ForeignKey('runs.id'))

    run = relationship('Run', backref=backref('nodes'))


class Tag(TableBase):
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))

    task_id = Column(Integer, ForeignKey('tasks.id'))

    task = relationship('Task', backref=backref('tags'))
