#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed without the express
#  * permission of CloudRunner.io
#  *******************************************************/

import json
import os

from cloudrunner import LIB_DIR
from cloudrunner_server.plugins.args_provider import ArgsProvider
from cloudrunner_server.plugins.jobs.base import JobInOutProcessorPluginBase
from cloudrunner.core.exceptions import (InterruptStep, InterruptExecution)


class ConditionalPlugin(JobInOutProcessorPluginBase, ArgsProvider):

    def __init__(self):
        pass

    def before(self, user_org, session_id, script, env, args, ctx, **kwargs):
        if args.if_continue and not args.if_continue in env:
            raise InterruptStep

        if args.if_not_continue and args.if_not_continue in env:
            raise InterruptStep

        if args.if_not_stop and not args.if_not_stop in env:
            raise InterruptExecution

        if args.if_stop and args.if_stop in env:
            raise InterruptExecution

        return (script, env)

    def after(self, user_org, session_id, job_id, env, response, args, ctx,
              **kwargs):
        # Nothing to do here
        return True

    def append_args(self):
        return [
            dict(arg='--if-continue', dest='if_continue'),
            dict(arg='--if-not-continue', dest='if_not_continue'),
            dict(arg='--if-stop', dest='if_stop'),
            dict(arg='--if-not-stop', dest='if_not_stop'),
        ]
