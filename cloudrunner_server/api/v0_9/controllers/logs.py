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

from datetime import datetime
import json
import logging
from pecan import expose, request
from pecan.core import override_template
from pecan.hooks import HookController
import re
from sqlalchemy.orm import exc, joinedload

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.hooks.redis_hook import RedisHook
from cloudrunner_server.api.model import (Script, Task, TaskGroup, Run,
                                          Revision, RunNode, LOG_STATUS)
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.util.cache import CacheRegistry

LOG = logging.getLogger()
PAGE_SIZE = 50


class Logs(HookController):

    __hooks__ = [ErrorHook(), DbHook(), RedisHook(),
                 PermHook(dont_have=set(['is_super_admin']))]

    @expose('json')
    def all(self, start=None, end=None, nodes=None, run_uuids=None, etag=None):
        start = int(start or 0) or 0
        if etag:
            etag = float(etag)
        else:
            etag = 0
        if start and not end:
            end = start + PAGE_SIZE
        else:
            end = PAGE_SIZE
        if end - start > 100:
            return O.error(msg="Page size cannot be bigger than 100")

        cache = CacheRegistry(redis=request.redis)
        max_score = 0
        uuids = []
        with cache.reader(request.user.org) as c:
            if etag:
                max_score, uuids = c.get_uuid_by_score(min_score=etag)

        if run_uuids:
            run_uuids = run_uuids.split(",")
            if uuids:
                uuids = set(run_uuids).intersection(set(uuids))
            else:
                uuids = run_uuids
        groups = TaskGroup.unique(request).order_by(Task.created_at.desc())
        ts = None
        if etag:
            ts = datetime.utcfromtimestamp(etag)
            groups = groups.filter(Task.created_at >= ts)
        if uuids:
            groups = groups.filter(Run.uuid.in_(uuids))
        if nodes:
            nodes = nodes.split(',')
            groups = groups.filter(RunNode.name.in_(nodes))
        group_ids = groups.all()[start:end]
        tasks = Task.visible(request).filter(
            Task.taskgroup_id.in_([g[0] for g in group_ids]))

        # if tags:
        #    tag_names = [tag.strip() for tag in re.split('[\s,;]', tags)
        #                 if tag.strip()]
        #    tasks = tasks.filter(Tag.name.in_(tag_names)).group_by(
        #        Task.id).having(func.count(Task.id) == len(tag_names))

        # tasks = sorted(tasks.all(), key=lambda t: t.parent_id, reverse=True)
        tasks = tasks.all()

        task_list = []
        task_map = {}

        def serialize(t):
            return t.serialize(
                skip=['owner_id', 'revision_id',
                      'full_script', 'timeout', 'taskgroup_id'],
                rel=[('taskgroup_id', 'group'),
                     ('script_content.script.full_path', 'name'),
                     ('script_content.version', 'revision'),
                     ('owner.username', 'owner'),
                     ('runs', 'nodes', map_nodes)])

        def walk(t):
            ser = serialize(t)
            task_map[t.id] = ser
            if not t.parent_id:
                if t.group.batch:
                    ser['batch'] = t.group.batch.serialize()
                else:
                    ser['batch'] = {}
                task_list.append(ser)
                task_map[t.id] = ser
            else:
                parent = task_map.get(t.parent_id)
                if parent and not any([s for s in parent.get("subtasks", [])
                                       if s['id'] == ser['id']]):
                    parent.setdefault("subtasks", []).append(ser)
            for sub in t.children:
                walk(sub)

        for t in tasks:
            walk(t)
        return O.tasks(etag=max_score,
                       groups=sorted(task_list, key=lambda t: t['created_at'],
                                     reverse=True))

    @expose('json')
    def get(self, group_id=None, task_ids=None, run_uuids=None,
            nodes=None, etag=None, script_name=None):
        try:
            groups = TaskGroup.unique(request).order_by(Task.created_at.desc())
            if group_id:
                groups = groups.filter(TaskGroup.id == group_id)
            else:
                if run_uuids:
                    run_uuids = run_uuids.split(',')
                    groups = groups.filter(Run.uuid.in_(run_uuids))
                if nodes:
                    nodes = nodes.split(',')
                    groups = groups.filter(RunNode.name.in_(nodes))
                if script_name:
                    scr = Script.find(request, script_name).one()
                    groups = groups.join(Revision,
                                         Script).filter(Script.id == scr.id)
            ts = None
            if etag:
                ts = datetime.utcfromtimestamp(etag)
                groups = groups.filter(Task.created_at >= ts)
            group = groups.first()
            if not group:
                return O.task()
            group = group[0]
            tasks = Task.visible(request).filter(
                Task.taskgroup_id == group)

            if task_ids:
                task_ids = task_ids.split(",")
                tasks = tasks.filter(Task.uuid.in_(task_ids))

            tasks = tasks.all()

            batch = {'workflows': []}
            for task in tasks:
                data = dict(created_at=task.created_at,
                            exit_code=task.exit_code,
                            uuid=task.uuid,
                            status=LOG_STATUS.from_value(task.status),
                            timeout=task.timeout)

                data['runs'] = []
                for r in task.runs:
                    to_skip = ['id', 'task_id', 'exec_user_id']
                    rels = [('nodes', 'nodes', map_nodes2),
                            ('env_out', 'env_out', lambda e: e or {}),
                            ('env_in', 'env_in', lambda e: safe_load(e))]
                    if r.exec_user_id != int(request.user.id):
                        to_skip.extend(['env_in', 'env_out', 'full_script'])
                    data['runs'].append(r.serialize(skip=to_skip,
                                                    rel=rels))
                data['runs'] = sorted(data['runs'],
                                      key=lambda _r: _r['step_index'])
                batch['workflows'].append(data)
            return O.group(**batch)
        except exc.NoResultFound, ex:
            LOG.error(ex)
            request.db.rollback()
        return O.error(msg="Log not found")

    @expose('json', content_type="application/json")
    @expose('include/raw.html', content_type="text/plain")
    def output(self, uuid=None, tail=100, nodes=None,
               show=None, template=None, content_type="text/html", **kwargs):
        try:
            tail = int(tail)
            if tail == -1:
                tail = None
        except ValueError:
            return O.error(msg="Wrong value for tail. Must be an integer >= 0")
        start = 0
        end = 50

        uuids = []
        pattern = kwargs.get('filter')
        order_by = kwargs.get('order', 'desc')

        q = Task.visible(request).join(Run, Task.runs).outerjoin(
            RunNode, Run.nodes).options(
                joinedload(Task.runs))

        if uuid:
            uuids.extend(re.split('[\s,;]', uuid))
            q = q.filter(Run.uuid.in_(uuids))

        if nodes:
            nodes = [re.split('[\s,;]', nodes)]
            q = q.filter(RunNode.name.in_(nodes))

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
            tasks = q.all()[start: end]
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg="Error loading logs")

        runs = []
        if not uuids:
            for t in tasks:
                uuids.extend([r.uuid for r in t.runs])
                runs.extend(t.runs)
        else:
            for t in tasks:
                runs.extend([r for r in t.runs if r.uuid in uuids])

        outputs = []
        with cache.reader(request.user.org) as c:
            try:
                c.apply_filters(pattern=pattern, target=show,
                                node=nodes,
                                before=kwargs.get('B'),
                                after=kwargs.get('A'))
            except ValueError:
                return O.error(msg="Wrong regex pattern")

            score, logs = c.load_log(min_score, max_score,
                                     uuids=uuids, tail=tail)
            for uuid in uuids:
                log_data = logs.get(uuid, [])
                if not log_data:
                    continue
                run = filter(lambda r: r.uuid == uuid, runs)[0]

                include = True
                if pattern:
                    include = bool(any([data for data in log_data.values()
                                        if data['lines']]))
                if include:
                    outputs.append(dict(
                        created_at=run.task.created_at,
                        status='running' if run.exit_code == -99
                        else 'finished',
                        etag=float(score),
                        uuid=uuid,
                        task_id=run.task.uuid,
                        screen=log_data))

        return O.outputs(_list=outputs)


def map_nodes(runs):
    for r in runs:
        return [dict(name=n.name, exit=n.exit_code) for n in r.nodes]


def map_nodes2(nodes):
    return [dict(name=n.name, exit=n.exit_code) for n in nodes]


def safe_load(j):
    try:
        return json.loads(j)
    except:
        return j
