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

from pecan import conf, request

from cloudrunner_server.api.hooks.redis_hook import RedisHook


class SignalHook(RedisHook):

    priority = 100

    def after(self, state):
        sig = getattr(state.response, 'fire_up_event', None)
        if sig:
            if conf.app.debug:
                state.response.headers['X-Pecan-Fire-Signal'] = sig
            request.redis.incr(sig)
            request.redis.publish(sig, state.response.fire_up_id)
