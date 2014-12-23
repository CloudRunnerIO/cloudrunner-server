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

from pecan import expose, request
from pecan.hooks import HookController

from cloudrunner_server.triggers.manager import TriggerManager

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.redis_hook import RedisHook
from cloudrunner_server.api.hooks.zmq_hook import ZmqHook
from cloudrunner_server.api.util import JsonOutput as O

MAN = TriggerManager()


class Dispatch(HookController):

    __hooks__ = [DbHook(), ZmqHook(), ErrorHook(), RedisHook()]

    @expose('json')
    def active_nodes(self):
        msg = request.zmq("list_active_nodes")
        if getattr(msg, 'control', '') == 'NODES':
            return O.nodes(_list=msg.nodes)
        return O.nodes(_list=[])
