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

from cloudrunner_server.api.hooks.braintree_hook import BrainTreeHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.util import JsonOutput as O


class Billing(HookController):

    __hooks__ = [DbHook(), ErrorHook(), BrainTreeHook()]

    @expose('json')
    def token(self):
        token = request.braintree.ClientToken.generate()
        return O.billing(token=token)
