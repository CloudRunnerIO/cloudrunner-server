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
