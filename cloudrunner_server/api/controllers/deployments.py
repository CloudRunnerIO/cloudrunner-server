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
from pecan import expose, request
from pecan.hooks import HookController

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.model import Deployment, Script
from cloudrunner_server.util.parser import DeploymentParser
from cloudrunner_server.triggers.manager import TriggerManager

MAN = TriggerManager()

# from cloudrunner_server.plugins.clouds import BaseCloudProvider


class Deployments(HookController):

    __hooks__ = [DbHook(), ErrorHook()]

    @expose('json', generic=True)
    @wrap_command(Deployment)
    def deployments(self, name=None, **kwargs):
        skip = ['id', 'owner_id']
        if name:
            depl = Deployment.my(request).filter(
                Deployment.name == name).first()
            if depl:
                return O.deployment(**depl.serialize(skip=skip))
            else:
                return O.error(msg="Cannot find deployment '%s'" % name)
        else:
            depl = [d.serialize(skip=skip)
                    for d in Deployment.my(request).all()]
            return O._anon(deployments=depl)
        return O.none()

    @deployments.when(method='POST', template='json')
    @deployments.wrap_create(integrity_error=lambda er:
                             "Duplicate deployment name")
    def create(self, name, **kwargs):
        if request.method != "POST":
            return O.none()
        name = name or kwargs['name']

        try:
            if isinstance(kwargs['content'], dict):
                content = kwargs['content']
            else:
                content = json.loads(kwargs['content'])
            content['steps']  # validate data
            if not isinstance(content['steps'], list):
                return O.error(msg="Missing steps in content")
            for step in content['steps']:
                step['target']  # validate data
                step['content']  # validate data
        except KeyError, kerr:
            return O.error(msg="Missing content data: %s" % kerr)
        depl = Deployment(name=name, content=json.dumps(content),
                          status='Pending',
                          owner_id=request.user.id)
        request.db.add(depl)

    @deployments.when(method='PATCH', template='json')
    @deployments.wrap_modify()
    def patch(self, name=None, **kwargs):
        name = name or kwargs['name']
        depl = Deployment.my(request).filter(Deployment.name == name).first()
        if not depl:
            return O.error(msg="Cannot find deployment '%s'" % name)
        if isinstance(kwargs['content'], dict):
            content = kwargs['content']
        else:
            content = json.loads(kwargs['content'])

        content['steps']  # validate data
        for step in content['steps']:
            step['target']  # validate data
            step['content']  # validate data
        depl.content = "%s\n%s" % (depl.content, json.dumps(content))
        return O.success(msg="Patched")

    @deployments.when(method='DELETE', template='json')
    @deployments.wrap_delete()
    def delete(self, name, **kwargs):
        depl = Deployment.my(request).filter(Deployment.name == name).first()
        if not depl:
            return O.error(msg="Cannot find deployment '%s'" % name)
        request.db.delete(depl)

    @expose('json', generic=True)
    @wrap_command(Deployment, method='start')
    def start(self, name, *args, **kwargs):
        name = name or kwargs['name']

        depl = Deployment.my(request).filter(Deployment.name == name).first()
        if not depl:
            return O.error(msg="Cannot find deployment '%s'" % name)

        steps = DeploymentParser(depl.content)
        if steps and kwargs.get('env'):
            # Override ENV

            if isinstance(kwargs['env'], dict):
                env = kwargs['env']
            else:
                env = json.loads(kwargs['env'])
            steps[0].env.update(env)

        task_ids = []
        for step in steps:
            # Run step
            if step.path:
                repo, _dir, scr_name, rev = Script.parse(step.path)
                scr = Script.find(request, step.path).one()
                if not scr:
                    return O.error(msg="Script '%s' not found" % step.path)

                content = scr.contents(request, rev=rev)
                if not content:
                    if rev:
                        return O.error(
                            msg="Version %s of script '%s' not found" %
                            (rev, step.path))
                    else:
                        return O.error(
                            msg="Script contents for '%s' not found" %
                            step.path)

            user_id = request.user.id
            task_ids.append(MAN.execute(user_id=user_id,
                                        content=content,
                                        db=request.db,
                                        env=step.env,
                                        **kwargs))

        return O.success(msg="Started", task_ids=task_ids)

    @expose('json', generic=True)
    @wrap_command(Deployment, method='restart')
    def restart(self, name, **kwargs):
        name = name or kwargs['name']
        if request.method != "POST":
            return O.none()
        return O.success(msg="Restarted")

    @expose('json', generic=True)
    @wrap_command(Deployment, method='start')
    def apply(self, *args, **kwargs):
        if request.method != "POST":
            return O.none()

        if isinstance(kwargs['content'], dict):
            content = kwargs['content']
        else:
            content = json.loads(kwargs['content'])
        for step in content['steps']:
            step['target']  # validate data
            step['content']  # validate data

        return O.success(msg="Started")
