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
from cloudrunner_server.api.model import Session


class DbHook(PecanHook):

    priority = 2

    def before(self, state):
        state.request.db = Session

    def after(self, state):
        if hasattr(state.request, 'db'):
            state.request.db.commit()

    def on_error(self, state, exc):
        if hasattr(state.request, 'db'):
            state.request.db.rollback()
