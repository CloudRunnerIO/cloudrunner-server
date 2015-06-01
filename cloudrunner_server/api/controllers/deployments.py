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
from pecan import expose, request, conf
from pecan.hooks import HookController

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.model import Deployment, User, Revision, Node
from cloudrunner_server.master.functions import CertController
from cloudrunner_server.plugins.clouds.base import BaseCloudProvider
from cloudrunner_server.triggers.manager import TriggerManager
from cloudrunner_server.util import parser

MAN = TriggerManager()
LOG = logging.getLogger()


class Deployments(HookController):

    __hooks__ = [DbHook(), ErrorHook()]

    @expose('json', generic=True)
    @wrap_command(Deployment)
    def deployments(self, name=None, **kwargs):
        skip = ['id', 'owner_id']

        def _encode(s):
            try:
                return json.loads(s)
            except ValueError:
                return {}
        if name:
            depl = Deployment.my(request).filter(
                Deployment.name == name).first()
            if depl:
                return O.deployment(**depl.serialize(
                    skip=skip,
                    rel=[('content', 'content',
                          lambda p: _encode(p))]))
            else:
                return O.error(msg="Cannot find deployment '%s'" % name)
        else:
            depl = sorted([d.serialize(skip=skip)
                           for d in Deployment.my(request).all()],
                          key=lambda d: d['name'])
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
            user = User.visible(request).filter(
                User.id == request.user.id).first()
            content = kwargs.pop('content')

            if not isinstance(content, dict):
                content = json.loads(content)

            _validate(content)

        except KeyError, kerr:
            return O.error(msg="Missing content data: %s" % kerr)
        depl = Deployment(name=name, content=json.dumps(content),
                          status='Pending',
                          owner=user)
        request.db.add(depl)

    """
    @deployments.when(method='PATCH', template='json')
    @deployments.wrap_modify()
    def patch(self, name=None, **kwargs):
        name = name or kwargs['name']
        depl = Deployment.my(request).filter(Deployment.name == name).first()
        if not depl:
            return O.error(msg="Cannot find deployment '%s'" % name)
        content = kwargs.pop('content')
        if not isinstance(content, dict):
            content = json.loads(content)

        depl.status = 'Patching'
        if "new_name" in kwargs:
            depl.name = kwargs["new_name"]
        request.db.commit()

        _validate(content)
        new_content = json.loads(depl.content)

        for step in content['steps']:
            new_content['steps'].append(step)

        depl.content = json.dumps(new_content)
        task_ids = _execute(depl, **kwargs)
        return O.success(msg="Patched", task_ids=task_ids)
    """

    @deployments.when(method='PUT', template='json')
    @deployments.wrap_modify()
    def rebuild(self, name, **kwargs):
        name = name or kwargs['name']
        depl = Deployment.my(request).filter(Deployment.name == name).first()
        if not depl:
            return O.error(msg="Cannot find deployment '%s'" % name)
        content = kwargs.pop('content')
        if not isinstance(content, dict):
            content = json.loads(content)

        depl.status = 'Rebuilding'
        if "new_name" in kwargs:
            depl.name = kwargs["new_name"]
        request.db.commit()

        _validate(content)
        depl.content = json.dumps(content)

        task_ids = _execute(depl, **kwargs)

        return O.success(status="ok", task_ids=task_ids)

    @deployments.when(method='DELETE', template='json')
    @deployments.wrap_delete()
    def delete(self, name, **kwargs):
        depl = Deployment.my(request).filter(Deployment.name == name).first()
        if not depl:
            return O.error(msg="Cannot find deployment '%s'" % name)
        _cleanup(depl)
        request.db.delete(depl)

    @expose('json', generic=True)
    @wrap_command(Deployment, method='start')
    def start(self, name, *args, **kwargs):
        name = name or kwargs['name']

        depl = Deployment.my(request).filter(Deployment.name == name).first()
        if not depl:
            return O.error(msg="Cannot find deployment '%s'" % name)
        if depl.status not in ['Pending', 'Stopped']:
            return O.error(msg="Deployment must be Pending or Stopped "
                           "to be Started.")

        content = json.loads(depl.content)
        _validate(content)
        request.db.commit()
        depl.status = "Starting"
        task_ids = _execute(depl, **kwargs)

        return O.success(status="ok", task_ids=task_ids)

    @expose('json', generic=True)
    @wrap_command(Deployment, method='start')
    def restart(self, name, *args, **kwargs):
        name = name or kwargs['name']

        depl = Deployment.my(request).filter(Deployment.name == name).first()
        if not depl:
            return O.error(msg="Cannot find deployment '%s'" % name)

        content = json.loads(depl.content)
        _validate(content)
        request.db.commit()
        depl.status = "Starting"
        task_ids = _execute(depl, **kwargs)

        return O.success(status="ok", task_ids=task_ids)

    @expose('json', generic=True)
    @wrap_command(Deployment, method='stop')
    def stop(self, name, *args, **kwargs):
        name = name or kwargs['name']

        depl = Deployment.my(request).filter(Deployment.name == name).first()
        if not depl:
            return O.error(msg="Cannot find deployment '%s'" % name)
        depl.status = "Stopped"
        _cleanup(depl)


def _validate(content):
    content['steps']  # validate data
    for step in content['steps']:
        step['target']  # validate data
        assert isinstance(step['target'], list)
        step['content']  # validate data


def _execute(depl, **kwargs):
    dep = parser.DeploymentParser(conf, request)
    dep.parse(depl)
    if dep.steps and kwargs.get('env'):
        # Override ENV

        if isinstance(kwargs['env'], dict):
            env = kwargs['env']
        else:
            env = json.loads(kwargs['env'])
        dep.steps[0].env.update(env)

    # clean-up resources
    _cleanup(depl)
    task_ids = []
    user_id = request.user.id
    temp_content = Revision(content=json.dumps(dep.content), version='HEAD')
    request.db.add(temp_content)
    # request.db.commit(    )
    task_ids = MAN.execute(user_id, dep,
                           revision=temp_content,
                           db=request.db,
                           **kwargs)
    if task_ids:
        task_ids.pop('group', None)
        task_ids.pop('parent_uid', None)

    return task_ids


def _cleanup(depl):
    cert = CertController(conf.cr_config)
    for res in depl.resources:
        provider_class = BaseCloudProvider.find(res.profile.type)
        if not provider_class:
            raise ValueError("Cloud profile with type: %s not found!" %
                             res.profile.type)
        provider = provider_class(res.profile)
        LOG.info("Cleaning instance[%s::%s] for node '%s'" % (
            provider.type, res.server_id, res.server_name))
        meta = {}
        if res.meta:
            meta = json.loads(res.meta)
        r = provider.delete_machine([res.server_id], **meta)
        if r == BaseCloudProvider.OK:
            LOG.info("Delete machine response: %s" % r)
        else:
            LOG.error("Cannot delete remote instance[%s::%s] for node '%s'" % (
                provider.type, res.server_id, res.server_name))
        request.db.delete(res)
        node = Node.visible(request).filter(
            Node.name == res.server_name).first()
        if node:
            LOG.info("Revoke node: %s" % node.name)
            [m[1] for m in cert.revoke(node.name, ca=request.user.org)]
            request.db.delete(node)
        else:
            LOG.warn("Local Node with name '%s' not found" % res.server_name)
