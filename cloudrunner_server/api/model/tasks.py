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
from sqlalchemy import (Column, String, Integer, DateTime, ForeignKey, Text)
from sqlalchemy.orm import relationship, backref, joinedload


from .base import TableBase
from .users import User, Org
from .library import Revision, Script, Folder
from .triggers import Job


from cloudrunner.util import Enum

LOG_STATUS = Enum('Unknown', 'Running', 'Finished')


class TaskGroup(TableBase):
    __tablename__ = 'taskgroups'

    id = Column(Integer, primary_key=True)


class Task(TableBase):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True)
    uuid = Column(String(40), index=True, unique=True)
    created_at = Column(DateTime, default=func.now())
    status = Column(Integer)
    timeout = Column(Integer)
    exit_code = Column(Integer)
    target = Column(Text)
    lang = Column(String(100))
    env_in = Column(Text)
    env_out = Column(Text)
    full_script = Column(Text)
    step = Column(Integer)
    total_steps = Column(Integer)

    owner_id = Column(Integer, ForeignKey('users.id'))
    taskgroup_id = Column(Integer, ForeignKey(TaskGroup.id))
    parent_id = Column(Integer, ForeignKey('tasks.id'))
    revision_id = Column(Integer, ForeignKey('revisions.id'))
    started_by_id = Column(Integer, ForeignKey('jobs.id'))

    owner = relationship('User')
    script_content = relationship(Revision)
    group = relationship(TaskGroup, backref=backref('tasks'))
    parent = relationship('Task',
                          remote_side=[id],
                          backref=backref('children'))
    started_by = relationship(Job)

    @staticmethod
    def visible(ctx):
        return ctx.db.query(Task).join(
            User, Org).options(
                joinedload(Task.script_content).
                joinedload(Revision.script).
                joinedload(Script.folder).
                joinedload(Folder.repository),
                joinedload(Task.started_by)).filter(
                    Org.name == ctx.user.org)

    def is_visible(self, request):
        if self.owner_id == int(request.user.id):
            return True

        return not self.script_content.script.folder.repository.private


class Tag(TableBase):
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))

    task_id = Column(Integer, ForeignKey('tasks.id'))

    task = relationship('Task', backref=backref('tags'))
