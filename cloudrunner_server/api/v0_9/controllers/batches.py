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

import json
import logging
from pecan import expose, request
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.model import (Script, Revision, Folder,
                                          Batch, ScriptStep, Condition)
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
            request.db.rollback()
            return O.error(msg="Batch is not valid", fields=batch_obj.errors)

        script = Script(name=name,
                        mime_type='text/batch',
                        owner_id=request.user.id,
                        folder=folder,
                        batch=batch_obj)
        request.db.add(script)
        request.db.commit()
        rev = Revision(content=json.dumps(batch), script_id=script.id)
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
            request.db.rollback()
            return O.error(msg="Batch is not valid", fields=batch_obj.errors)

        script = Script.find(request, path).one()
        new_name = batch.get('new_name')
        if new_name:
            if not Script.valid_name(new_name):
                request.db.rollback()
                return O.error(msg="Invalid script name")
            script.name = new_name

        script.mime_type = 'text/batch'
        if script.batch:
            request.db.delete(script.batch)
        script.batch = batch_obj
        rev = Revision(content=json.dumps(batch), script_id=script.id)
        request.db.add(rev)

        if batch_obj.warnings:
            return O.success(status='ok',
                             warnings=batch_obj.warnings)


def _validate_batch(ctx, batch_data):
    b = Batch(private=bool(batch_data.get('private')))
    b.errors = []
    b.warnings = []
    ctx.db.add(b)

    for script in batch_data['scripts']:
        step = ScriptStep(script=Script.find(ctx, script['script']).one())
        if step.script.mime_type != 'text/workflow':
            b.errors.append("'%s' is not an workflow" % script['script'])
        _id = int(script['id'])
        step._id = _id
        step.root = _id == 0
        step.as_sudo = bool(script.get('as_sudo'))
        step.version = script.get('rev')
        ctx.db.add(step)
        b.scripts.append(step)

    root = [scr for scr in b.scripts if scr.root]
    if len(root) != 1:
        b.errors.append("Batch should have exactly 1 root step")

    for cond in batch_data['conditions']:
        c = Condition()
        c.type = cond['type']
        c.arguments = json.dumps(cond['arguments'])
        src = int(cond['src'])
        dst = int(cond['dst'])

        src_script = [j for i, j in enumerate(b.scripts) if j._id == src]
        if not src_script:
            b.errors.append('%s is not a valid script id' % src)
        else:
            src_script = src_script[0]
            c.source = src_script

        dst_script = [j for i, j in enumerate(b.scripts) if j._id == dst]
        if not dst_script:
            b.errors.append('%s is not a valid script id' % dst)
        else:
            dst_script = dst_script[0]
            c.destination = dst_script
        ctx.db.add(c)
        b.conditions.append(c)

    return b
