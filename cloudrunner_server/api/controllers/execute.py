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
import logging
from pecan import expose, request, abort
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.util import (JsonOutput as O, flatten_params)
from cloudrunner_server.api.model import (Script, Repository, ApiKey,
                                          Deployment)
from cloudrunner_server.triggers.manager import TriggerManager
from cloudrunner_server.api.util import Wrap
from cloudrunner_server.api.controllers.deployments import _execute

LOG = logging.getLogger()

MAN = TriggerManager()


def cached_user(user):
    return Wrap(id=user.id,
                username=user.username,
                org=user.org.name,
                email=user.email,
                permissions=user.permissions)


class Execute(HookController):

    __hooks__ = [DbHook()]

    @expose('json')
    def workflow(self, *args, **kwargs):
        full_path = "/" + "/".join(args)
        LOG.info("Received execute request [%s] from: %s" % (
            full_path, request.client_addr))

        if not getattr(request, "user", None):
            key = kwargs.pop('key', None)
            if not key:
                return O.error(msg="Missing auth key")

            api_key = get_api_key(key)
            if not api_key:
                return abort(401)
            user_id = api_key.user_id
            request.user = cached_user(api_key.user)
        else:
            user_id = request.user.id

        version = kwargs.pop("rev", None)
        repo, _dir, scr_name, rev = Script.parse(full_path)

        repo = request.db.query(Repository).filter(
            Repository.name == repo).first()
        if not repo:
            return O.error(msg="Repository '%s' not found" % repo)

        scr = Script.find(request, full_path).one()

        if not scr:
            return O.error(msg="Script '%s' not found" % full_path)
        rev = scr.contents(request, rev=version)
        if not rev:
            if version:
                return O.error(msg="Version %s of script '%s' not found" %
                               (version, full_path))
            else:
                return O.error(msg="Script contents for '%s' not found" %
                               full_path)

        env = kwargs.pop('env', {})
        env.update(flatten_params(request.params))
        request.db.commit()
        task_id = MAN.execute(user_id=user_id,
                              content=rev,
                              db=request.db,
                              env=env,
                              **kwargs)
        if task_id:
            return O.success(msg="Dispatched", **task_id)
        else:
            return O.error(msg="Cannot send request")

    @expose('json')
    def rebuild(self, name, *args, **kwargs):
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

        request.db.commit()
        task_ids = _execute(depl, **kwargs)

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
        task_ids = _execute(depl, **kwargs)

        return O.success(msg="Started", task_ids=task_ids)


def get_api_key(key):
    api_key = request.db.query(ApiKey).filter(
        ApiKey.value == key, ApiKey.enabled == True).first()  # noqa
    if api_key:
        api_key.last_used = datetime.utcnow()
        request.db.add(api_key)
        return api_key
