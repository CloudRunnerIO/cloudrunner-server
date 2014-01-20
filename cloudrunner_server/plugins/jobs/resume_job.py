#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 CloudRunner.IO
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import json
import os

from cloudrunner_server.plugins.args_provider import ArgsProvider
from cloudrunner_server.plugins.jobs.base import JobInOutProcessorPluginBase


class JobSavePluginEnv(JobInOutProcessorPluginBase, ArgsProvider):

    def __init__(self):
        self.log_dir = getattr(JobSavePluginEnv, 'log_dir', '/tmp/log_dir')

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
