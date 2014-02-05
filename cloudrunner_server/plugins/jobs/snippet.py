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
import logging
import os

from cloudrunner_server.plugins.args_provider import ArgsProvider
from cloudrunner_server.plugins.jobs.base import JobInOutProcessorPluginBase

LOG = logging.getLogger(__name__)


def _default_dir():
    from cloudrunner import LIB_DIR
    _def_dir = os.path.join(LIB_DIR, "cloudrunner",
                            "plugins", "snippet")
    if not os.path.exists(_def_dir):
        os.makedirs(_def_dir)
    return _def_dir


class SnippetSavePluginEnv(JobInOutProcessorPluginBase, ArgsProvider):

    def __init__(self):
        self.file_dir = getattr(SnippetSavePluginEnv, 'file_dir',
                                _default_dir())

    def before(self, user_org, session_id, script, env, args, ctx, **kwargs):
        if args.save:
            file_name = ''.join([user_org[1], user_org[0],
                                 '~', args.save, '.snp'])
            snippet_file = os.path.join(self.file_dir, file_name)
        return (script, env)

    def after(self, user_org, session_id, job_id, env, response, args, ctx,
              **kwargs):
        return True

    def append_args(self):
        return dict(arg='--save', dest='save')


class SnippetLoadPluginEnv(JobInOutProcessorPluginBase, ArgsProvider):

    def __init__(self):
        self.file_dir = getattr(SnippetLoadPluginEnv, 'file_dir',
                                _default_dir())

    def before(self, user_org, session_id, script, env, args, ctx, **kwargs):
        if args.load:
            file_name = ''.join([user_org[1], user_org[0],
                                 '~', args.save, '.snp'])
            snippet_file = os.path.join(self.file_dir, file_name)
            try:
                snippet_content = open(snippet_file).read()
                return [script, snippet_content], env
            except Exception, ex:
                LOG.exception(ex)
        return (script, env)

    def after(self, user_org, session_id, job_id, env, response, args, ctx,
              **kwargs):
        return True

    def append_args(self):
        return dict(arg='--load', dest='load')
