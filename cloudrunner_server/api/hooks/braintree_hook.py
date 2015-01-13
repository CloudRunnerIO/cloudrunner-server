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

import braintree

from pecan import request
from pecan.hooks import PecanHook
from cloudrunner_server.api.model import Session


class BrainTreeHook(PecanHook):

    priority = 300

    def before(self, state):
        state.request.db = Session
        braintree.Configuration.configure(
            braintree.Environment.Sandbox,
            "yfvc86vtgs6q5ybq",
            "t4bzcv4jcjdrwspg",
            "7fb4d9c563b098c44313fb73b48663f2"
        )
        request.braintree = braintree
