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
from pecan import expose, request, abort
from pecan.hooks import HookController
import re

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.util import (JsonOutput as O, flatten_params)
from cloudrunner_server.api.model import (ApiKey, Deployment, User)
from cloudrunner_server.triggers.manager import TriggerManager
from cloudrunner_server.api.util import Wrap
from cloudrunner_server.api.controllers.deployments import _execute

LOG = logging.getLogger()
MAN = TriggerManager()
SPLITTER = re.compile("[\s,;]")


def cached_user(user):
    return Wrap(id=user.id,
                username=user.username,
                org=user.org.name,
                email=user.email,
                permissions=user.permissions)


class Execute(HookController):

    __hooks__ = [DbHook()]

    @expose('json')
    def script(self, *args, **kwargs):
        full_path = "/" + "/".join(args)
        LOG.info("Received execute script request [%s] from: %s" % (
            full_path, request.client_addr))

        key = kwargs.pop('key', None)
        if not getattr(request, "user", None):
            if not key:
                return O.error(msg="Missing auth key")

            api_key = get_api_key(key)
            if not api_key:
                return abort(401)
            user_id = api_key.user_id
            request.user = cached_user(api_key.user)
        else:
            user_id = request.user.id
        user = request.db.query(User).filter(User.id == user_id).one()

        targets = kwargs.pop("targets")
        if not targets:
            return O.error(msg="Targets is a mandatory field")
        targets = [t.strip() for t in SPLITTER.split(targets) if t.strip()]

        env = kwargs.pop('env', {})

        env.update(flatten_params(request.params))
        dep_data = dict()
        dep_data['steps'] = []
        step = dict(target=targets,
                    content=dict(path=full_path))
        dep_data['steps'].append(step)

        depl = Deployment(name="Execute: %s" % full_path,
                          content=json.dumps(dep_data),
                          status='Pending',
                          owner=user)

        task_ids = _execute(depl, env=env, dont_save=True, **kwargs)
        if task_ids:
            return O.success(status="ok", **task_ids)
        else:
            return O.error(msg="Cannot execute script")

    @expose('json')
    def rebuild(self, name, *args, **kwargs):
        kwargs = kwargs or request.json
        LOG.info("Received rebuild job [%s] from: %s" % (
            name, request.client_addr))

        key = kwargs.pop('key', None)
        if not getattr(request, "user", None):
            if not key:
                return O.error(msg="Missing auth key")

            api_key = get_api_key(key)
            if not api_key:
                return abort(401)
            request.user = cached_user(api_key.user)

        depl = request.db.query(Deployment).filter(
            Deployment.name == name).first()
        if not depl:
            return O.error(msg="Deployment '%s' not found" % depl)

        request.db.commit()
        task_ids = _execute(depl, env=kwargs)

        return O.success(msg="Restarted", task_ids=task_ids)

    @expose('json')
    def start(self, name, *args, **kwargs):
        kwargs = kwargs or request.json
        LOG.info("Received rebuild job [%s] from: %s" % (
            name, request.client_addr))

        if not getattr(request, "user", None):
            key = kwargs.pop('key', None)
            if not key:
                return O.error(msg="Missing auth key")

            api_key = get_api_key(key)
            if not api_key:
                return abort(401)
            request.user = cached_user(api_key.user)

        depl = request.db.query(Deployment).filter(
            Deployment.name == name).first()
        if not depl:
            return O.error(msg="Deployment '%s' not found" % depl)
        if depl.status not in ['Pending', 'Stopped']:
            return O.error(msg="Deployment must be Pending or Stopped "
                           "to be Started.")

        request.db.commit()
        task_ids = _execute(depl, env=kwargs)

        return O.success(msg="Started", task_ids=task_ids)


def get_api_key(key):
    api_key = request.db.query(ApiKey).filter(
        ApiKey.value == key, ApiKey.enabled == True).first()  # noqa
    if api_key:
        api_key.last_used = datetime.utcnow()
        request.db.add(api_key)
        return api_key
