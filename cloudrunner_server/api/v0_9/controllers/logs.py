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

import logging
from pecan import expose, request
from pecan.core import override_template
from pecan.hooks import HookController
import re
from sqlalchemy.orm import exc, joinedload
from sqlalchemy import func

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.hooks.redis_hook import RedisHook
from cloudrunner_server.api.model import (Script, Task, Tag, Revision,
                                          LOG_STATUS, SOURCE_TYPE)
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.util.cache import CacheRegistry

LOG = logging.getLogger()
PAGE_SIZE = 50


class Logs(HookController):

    __hooks__ = [ErrorHook(), DbHook(), RedisHook(),
                 PermHook(dont_have=set(['is_super_admin']))]

    @expose('json')
    def all(self, start=None, end=None, tags=None, etag=None):
        start = int(start or 0) or 0
        etag = etag or 0
        end = int(end or PAGE_SIZE)
        if end - start > 100:
            return O.error(msg="Page size cannot be bigger than 100")

        tasks = Task.visible(request).filter(
            Task.parent_id == None).options(
            joinedload(Task.children)).order_by(Task.id.desc())  # noqa

        if tags:
            tag_names = [tag.strip() for tag in re.split('[\s,;]', tags)
                         if tag.strip()]
            tasks = tasks.filter(Tag.name.in_(tag_names)).group_by(
                Task.id).having(func.count(Task.id) == len(tag_names))

        cache = CacheRegistry(redis=request.redis)
        max_score = 0
        with cache.reader(request.user.org) as c:
            if etag:
                max_score, uuids = c.get_uuid_by_score(min_score=etag)
                tasks = tasks.filter(Task.uuid.in_(uuids))
            else:
                max_score, uuids = c.get_uuid_by_score(min_score=etag)

        tasks = sorted(tasks.all()[start:end], key=lambda t: t.id)

        task_list = []
        task_map = {}

        def walk(t):
            ser = t.serialize(
                skip=['id', 'owner_id', 'revision_id',
                      'started_by_id', 'full_script', 'timeout', 'env_in',
                      'env_out'],
                rel=[('taskgroup_id', 'group'),
                     ('script_content.script.full_path', 'name'),
                     ('script_content.version', 'revision'),
                     ('started_by.name', 'job'),
                     ('started_by.source', 'source',
                      lambda x:SOURCE_TYPE.from_value(x) if x else ''),
                     ('owner.username', 'owner')])
            task_map[t.id] = ser
            if not t.parent_id:
                task_list.append(ser)
                task_map[t.id] = ser
            else:
                parent = task_map.get(t.parent_id)

                if parent:
                    parent.setdefault("subtasks", []).append(ser)
            for sub in t.children:
                walk(sub)

        for t in tasks:
            walk(t)

        return O.tasks(etag=max_score,
                       groups=sorted(task_list, key=lambda t: t['created_at'],
                                     reverse=True))

    @expose('json')
    def get(self, log_uuid=None):
        if not log_uuid:
            return O.error(msg="Selector not provided")
        try:
            task = Task.visible(request).filter(
                Task.uuid == log_uuid).one()
            data = dict(target=task.target,
                        selector=task.target,
                        lang=task.lang,
                        created_at=task.created_at,
                        exit_code=task.exit_code,
                        uuid=task.uuid,
                        status=LOG_STATUS.from_value(task.status),
                        timeout=task.timeout)

            if task.is_visible(request):
                data['script'] = task.full_script
            else:
                template = """
###
### Workflow: %s
### Owner: %s
###"""
                data['script'] = (template %
                                  (task.script_content.script.full_path(),
                                   task.owner.username)
                                  )
            if task.owner_id == request.user.id:
                data['env'] = task.env_in
            return O.task(**data)
        except exc.NoResultFound, ex:
            LOG.error(ex)
            request.db.rollback()
        return O.error(msg="Log not found")

    @expose('json', content_type="application/json")
    @expose('include/raw.html', content_type="text/plain")
    def output(self, uuid=None, script=None, tags=None, tail=100, steps=None,
               nodes=None, show=None, template=None, content_type="text/html",
               **kwargs):
        try:
            tail = int(tail)
        except ValueError:
            return O.error(msg="Wrong value for tail. Must be an integer >= 0")
        start = 0
        end = 50

        uuids = []
        if uuid:
            uuids.extend(re.split('[\s,;]', uuid))
        pattern = kwargs.get('filter')
        order_by = kwargs.get('order', 'desc')

        q = Task.visible(request)

        if script:
            scr = Script.find(request, script).one()
            q = q.join(Revision, Script).filter(Script.id == scr.id)
        """
        if tags:
            # get uuids from tag
            tag_names = [tag.strip() for tag in re.split('[\s,;]', tags)
                         if tag.strip()]
            # q = q.filter(Tag.name.in_(tag_names)).group_by(
            #     Task.id).having(func.count(Task.id) == len(tag_names))
        """
        if template:
            override_template("library:%s" % template,
                              content_type=content_type)

        # TODO: check for e-tag
        min_score = float(kwargs.get('from', request.headers.get('Etag', 0)))
        max_score = float(kwargs.get('to', 'inf'))
        cache = CacheRegistry(redis=request.redis)
        score = 1

        try:
            if order_by == 'asc':
                q = q.order_by(Task.created_at.asc())
            else:
                q = q.order_by(Task.created_at.desc())
            tasks = q.all()[start:end]
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg="Error loading logs")
        uuids = [t.uuid for t in tasks if t.uuid]

        outputs = []
        with cache.reader(request.user.org) as c:
            try:
                if nodes:
                    nodes = nodes.split(',')
                c.apply_filters(pattern=pattern, target=show,
                                node=nodes,
                                before=kwargs.get('B'),
                                after=kwargs.get('A'))
            except ValueError:
                return O.error(msg="Wrong regex pattern")

            score, logs = c.load_log(min_score, max_score, uuids=uuids)

            for uuid in uuids:
                log_data = logs.get(uuid, [])
                if not log_data:
                    continue
                task = filter(lambda t: t.uuid == uuid, tasks)[0]

                include = True
                if pattern:
                    has_lines = any([s for s in steps.values() if s['lines']])
                    if not has_lines:
                        include = False
                if include:
                    outputs.append(dict(
                        created_at=task.created_at,
                        status='running' if task.status == LOG_STATUS.Running
                        else 'finished',
                        etag=float(score),
                        uuid=uuid,
                        screen=log_data))

        return O.outputs(_list=outputs)
