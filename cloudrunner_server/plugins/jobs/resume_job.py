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


def _default_dir():
    _def_dir = os.path.join(LIB_DIR, "cloudrunner", "plugins", "resume_job")
    if not os.path.exists(_def_dir):
        os.makedirs(_def_dir)
    return _def_dir


class JobSavePluginEnv(JobInOutProcessorPluginBase, ArgsProvider):

    def __init__(self):
        self.log_dir = getattr(JobSavePluginEnv, 'log_dir', _default_dir())

    def before(self, user_org, session_id, script, env, args, ctx, **kwargs):
        if args.resume_id:
            return script, self._resume_env(user_org, args.resume_id) or env
        return (script, env)

    def after(self, user_org, session_id, job_id, env, response, args, ctx,
              **kwargs):
        file_name = ''.join([user_org[1], user_org[0], '~', job_id, '.job'])
        job_file = os.path.join(self.log_dir, file_name)
        try:
            open(job_file, 'w').write(json.dumps(env))
        except:
            if not os.path.exists(self.log_dir):
                # Ensure log dir is present
                os.makedirs(self.log_dir)
                # retry
                open(job_file, 'w').write(json.dumps(env))

        return True

    def append_args(self):
        return dict(arg='--resume', dest='resume_id')

    def _resume_env(self, user_org, job_id):
        file_name = ''.join([user_org[1], user_org[0], '~', job_id, '.job'])
        job_file = os.path.join(self.log_dir, file_name)
        try:
            return json.loads(open(job_file).read())
        except:
            return {}
