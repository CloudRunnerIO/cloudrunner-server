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

from collections import defaultdict
import logging
import msgpack
from pecan import expose, request
from pecan.core import override_template
from pecan.hooks import HookController
import re
from sqlalchemy.orm import exc
from sqlalchemy import func
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.hooks.redis_hook import RedisHook
from cloudrunner_server.api.model import (Step, User, Task,
                                          Tag, Org, LOG_STATUS)
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.util.cache import CacheRegistry

LOG = logging.getLogger()
PAGE_SIZE = 50


class Logs(HookController):

    __hooks__ = [ErrorHook(), DbHook(), RedisHook(),
                 PermHook(dont_have=set(['is_super_admin']))]

    @expose('json')
    def all(self, start=None, end=None, tags=None):
        start = int(start or 0) or 0
        end = int(end or PAGE_SIZE)
        if end - start > 100:
            return O.error(msg="Page size cannot be bigger than 100")

        tasks = Task.visible(request).order_by(Task.id)

        if tags:
            tag_names = [tag.strip() for tag in re.split('[\s,;]', tags)
                         if tag.strip()]
            tasks = tasks.filter(Tag.name.in_(tag_names)).group_by(
                Task.id).having(func.count(Task.id) == len(tag_names))
        tasks = tasks.all()[start:end]
        task_list = []
        task_map = {}

        def walk(task):
            ser = t.serialize(
                skip=['taskgroup_id', 'id', 'owner_id', 'revision_id',
                      'started_by_id'],
                rel=[('script_content.script.full_path', 'name'),
                     ('script_content.version', 'revision'),
                     ('started_by.name', 'job'),
                     ('owner.username', 'owner')])
            task_map[t.id] = ser
            if not t.parent_id:
                task_list.append(ser)
                task_map[t.id] = ser
            else:
                parent = task_map.get(t.parent_id)

                if parent:
                    parent.setdefault("subtasks", []).append(ser)

        for t in tasks:
            walk(t)

        return O.tasks(_list=sorted(task_list, key=lambda t: t['created_at'],
                                    reverse=True))

    @expose('json')
    def get(self, log_uuid=None):
        if not log_uuid:
            return O.error(msg="Selector not provided")
        try:
            log = request.db.query(Task).outerjoin(Step).filter(
                Task.owner_id == request.user.id,
                Task.uuid == log_uuid).one()
            steps = []
            if log.steps:
                for i, step in enumerate(sorted(log.steps,
                                                key=lambda s: s.id)):
                    steps.append(dict(index=i + 1,
                                      target=step.target,
                                      script=step.script,
                                      timeout=step.timeout,
                                      env_in=step.env_in))
            return O.log(
                created_at=log.created_at,
                timeout=log.timeout,
                exit_code=log.exit_code,
                uuid=log.uuid,
                status=LOG_STATUS.from_value(log.status),
                steps=steps,
            )
        except exc.NoResultFound, ex:
            LOG.error(ex)
            request.db.rollback()
        return O.error(msg="Log not found")

    @expose('json', content_type="application/json")
    @expose('include/raw.html', content_type="text/plain")
    def output(self, uuid=None, tags=None, tail=100, steps=None, nodes=None,
               show=None, template=None, content_type="text/html", **kwargs):

        log_uuid = uuid
        pattern = kwargs.get('filter')
        order_by = kwargs.get('order', 'desc')

        if template:
            override_template("library:%s" % template,
                              content_type=content_type)

        # TODO: check for e-tag
        min_score = int(kwargs.get('from') or request.headers.get('Etag', 0))
        max_score = int(kwargs.get('to', 0)) or 'inf'
        cache = CacheRegistry(redis=request.redis)
        score = 1
        if not log_uuid and not tags:
            return O.error(msg="Selector(uuid or tags) not provided")

        try:
            tail = int(tail)
        except ValueError:
            return O.error(msg="Wrong value for tail. Must be an integer >= 0")

        """
        if tail:
            begin = -tail
        else:
            begin = 0
        """

        try:
            q = request.db.query(Task).join(
                User, Org, Step).outerjoin(Tag).filter(
                    Org.name == request.user.org)
            if tags:
                tag_names = [tag.strip() for tag in re.split('[\s,;]', tags)
                             if tag.strip()]
                q = q.filter(Tag.name.in_(tag_names)).group_by(
                    Task.id).having(func.count(Task.id) == len(tag_names))
            else:
                q = q.filter(Task.uuid == log_uuid)

            if order_by == 'asc':
                q = q.order_by(Task.created_at.asc())
            else:
                q = q.order_by(Task.created_at.desc())
            print q
            logs = q.all()  # [start:end]
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg="Error loading logs")
        uuids = [l.uuid for l in logs if l.uuid]

        print ">??", uuids, logs
        outputs = []
        with cache.reader(request.user.org, *uuids) as c:
            try:
                if nodes:
                    nodes = nodes.split(',')
                if steps:
                    steps = steps.split(',')
                    steps = [str(int(s) - 1) for s in steps]
                c.apply_filters(pattern=pattern, target=show,
                                step_id=steps, node=nodes,
                                before=kwargs.get('B'),
                                after=kwargs.get('A'))
            except ValueError:
                return O.error(msg="Wrong regex pattern")

            score, frames_data = c.load(min_score, max_score)

            for uuid in uuids:
                frame_data = frames_data.get(uuid, [])
                if not frame_data:
                    continue
                steps = {}
                log = [l for l in logs if l.uuid == uuid][0]
                for frame in frame_data:
                    step_id = int(frame.header['step_id']) + 1
                    if step_id in steps:
                        step = steps[step_id]
                    else:
                        step = {"step": step_id, "lines": []}
                        steps[step_id] = step

                    if frame.frame_type == "I":
                        # Initial
                        pass
                    elif frame.frame_type == "B":
                        step['lines'].append(
                            [frame.ts, frame.header.get('src', 'O')] +
                            frame.body)
                        frame.header.pop('src')
                    elif frame.frame_type == "S":
                        # Summary
                        step.update(msgpack.unpackb(frame.body[0]))
                        step.pop('user')

                    step.update(frame.header)
                    step.pop('step_id')
                include = True
                if pattern:
                    has_lines = any([s for s in steps.values() if s['lines']])
                    if not has_lines:
                        include = False
                if include:
                    outputs.append(dict(
                        steps=sorted(steps.values(), key=lambda x: x['step']),
                        created_at=log.created_at,
                        status='running' if log.status == LOG_STATUS.Running
                        else 'finished',
                        etag=int(score),
                        uuid=uuid))

        return O.outputs(_list=outputs)

    @expose('json')
    def active(self):
        logs = request.db.query(Task).join(User, Org).filter(
            Org.name == request.user.org,
            Task.status == 1).all()

        res = [l.serialize(skip=['id', 'status', 'owner_id']) for l in logs]
        return O.active(_list=res)
