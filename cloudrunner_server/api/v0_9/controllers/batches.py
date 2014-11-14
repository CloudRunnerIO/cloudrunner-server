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

import abc
import json
import logging
from pecan import expose, request
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.model import Script, Revision, Folder
from cloudrunner_server.api.util import JsonOutput as O

LOG = logging.getLogger()


class Batches(HookController):

    __hooks__ = [ErrorHook(), DbHook(),
                 PermHook(dont_have=set(['is_super_admin']))]

    @expose('json', generic=True)
    @wrap_command(Script, model_name='Batch')
    def batch(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")
        path = '/'.join(args)
        rev = kwargs.get("rev")
        script = Script.find(request, path).one()

        revision = script.contents(request, rev=rev)
        batch = json.loads(revision.content)

        return O.batch(rev=revision.version, steps=batch)

    @batch.when(method='POST', template='json')
    @batch.wrap_create(model_name='Batch')
    def create(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")

        batch = request.json['batch']

        path = '/'.join(args)
        full_path, _, name = path.rpartition('/')
        if not Script.valid_name(name):
            return O.error(msg="Invalid batch name")

        repo, _, folder_path = full_path.partition('/')
        if not folder_path.startswith('/'):
            folder_path = "/" + folder_path
        folder_path = folder_path + "/"
        folder = Folder.editable(request, repo, folder_path).first()

        if not folder:
            return O.error("Folder not found")

        batch_obj = _validate_batch(request, batch)

        if batch_obj.errors:
            return O.error(msg="Batch is not valid", fields=batch_obj.errors)

        script = Script(name=name,
                        mime_type='text/batch',
                        owner_id=request.user.id,
                        folder=folder)
        request.db.add(script)
        request.db.commit()
        request._model_id = script.id

        rev = Revision(content=batch_obj.content, script_id=script.id)
        request.db.add(rev)

        if batch_obj.warnings:
            return O.success(status='ok',
                             warnings=batch_obj.warnings)

    @batch.when(method='PUT', template='json')
    @batch.wrap_update(model_name='Batch')
    def save(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")
        if not request.json:
            return O.error(msg="Data not provided")

        batch = request.json['batch']

        path = '/'.join(args)

        batch_obj = _validate_batch(request, batch)

        if batch_obj.errors:
            return O.error(msg="Batch is not valid", fields=batch_obj.errors)

        script = Script.find(request, path).one()
        new_name = batch.get('new_name')
        if new_name:
            if not Script.valid_name(new_name):
                return O.error(msg="Invalid script name")
            script.name = new_name
        script.mime_type = 'text/batch',

        rev = Revision(content=batch_obj.content, script_id=script.id)
        request.db.add(rev)

        if batch_obj.warnings:
            return O.success(status='ok',
                             warnings=batch_obj.warnings)


class Condition(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self):
        self.arguments = []
        self.source = None
        self.dest = None

    @classmethod
    def create(cls, _type):
        for sub in cls.__subclasses__():
            if sub.type == _type:
                return sub
        else:
            return None

    @abc.abstractmethod
    def context(self, task):
        raise NotImplemented()

    def evaluate(self, task):
        return bool(set(self.context(task)).intersection(set(self.arguments)))


class ExitCodeCondition(Condition):

    type = 'exit_code'

    def __init__(self):
        pass

    def context(self, task):
        return [task.exit_code]


class EnvCondition(Condition):

    type = 'env'

    def __init__(self):
        pass

    def context(self, task):
        return task.env.keys()


class Step(object):

    def __init__(self):
        self.id = None
        self.script = None
        self.as_sudo = False


class Batch1(object):

    def __init__(self):
        self.content = ''
        self.steps = []
        self.conditions = []
        self.warnings = []
        self.errors = []


def _validate_batch(ctx, batch_data):
    return {}
    b = Batch()
    b.content = json.dumps(batch_data)

    for script in batch['scripts']:
        s = Step()
        s.script = script['script']
        s.id = int(script['id'])
        s.as_sudo = bool(script.get('sudo'))
        b.steps.append(s)

    for cond in batch['conditions']:
        c = Condition.create(cond['type'])
        if not c:
            b.errors.append('%s is not a valid condition' % cond['type'])
            continue
        src = int(cond['src'])
        dst = int(cond['dst'])

        src_script = [i for i, j in enumerate(b.steps) if j.id == src]
        if not src_script:
            b.errors.append('%s is not a valid script id' % src)
        else:
            src_script = src_script[0]

        dst_script = [i for i, j in enumerate(b.steps) if j.id == dst]
        if not dst_script:
            b.errors.append('%s is not a valid script id' % dst)
        else:
            dst_script = dst_script[0]
        c.source = src_script
        c.dest = dst_script
        b.conditions.append(c)

    return b
