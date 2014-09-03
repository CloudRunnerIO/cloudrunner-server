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

from pecan.hooks import PecanHook
from cloudrunner_server.api.server import Master


class ZmqHook(PecanHook):

    priority = 101

    def before(self, state):
        def zmq(user):
            def wrapper(*args, **kwargs):
                return Master(user).command(*args, **kwargs)
            return wrapper

        state.request.zmq = zmq(state.request.user.username)

        def reset(user):
            state.request.zmq = zmq(user)

        state.request.reset_zmq = reset

    def after(self, state):
        return

    def on_error(self, state, exc):
        return
