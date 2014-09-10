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
from pecan import expose, request
from pecan.hooks import HookController

from cloudrunner_server.triggers.manager import TriggerManager

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.redis_hook import RedisHook
from cloudrunner_server.api.hooks.zmq_hook import ZmqHook
from cloudrunner_server.api.util import JsonOutput as O


class Dispatch(HookController):

    __hooks__ = [DbHook(), ZmqHook(), ErrorHook(), RedisHook()]

    @expose('json')
    def active_nodes(self):
        msg = request.zmq("list_active_nodes")
        return O.nodes(_list=msg.nodes)

    @expose('json')
    def execute(self, **kwargs):
        try:
            kw = None
            if request.headers['Content-Type'].find(
                    "x-www-form-urlencoded") >= 0:
                kw = kwargs
            else:
                try:
                    kw = request.json_body
                    kw.update(kwargs)
                except:
                    kw = kwargs

            script_name = kwargs.get("script_name")
            if not script_name:
                return O.error(msg="Script not passed")
            source = kwargs.get('source')
            if not source:
                now = datetime.now()
                source = 'Anonymous exec: %s' % now.isoformat()[:19]
            kw.pop('user_id', '')
            kw.pop('content', '')
            kw.pop('script_name', '')
            uuid = TriggerManager().execute(user_id=request.user.id,
                                            script_name=script_name, **kw)

        except KeyError, kerr:
            return O.error(msg="Missing value: %s" % kerr)
        return O.dispatch(uuid=uuid)

    @expose('json')
    def term(self, command):
        if not command or command.lower() not in ['term', 'quit']:
            return dict(error="Unknown termination command: %s" % command)
