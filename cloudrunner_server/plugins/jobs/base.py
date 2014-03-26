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

import abc


class JobInOutProcessorPluginBase(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def before(self, user, session_id, job_id, env, args, ctx, **kwargs):
        pass

    @abc.abstractmethod
    def after(self, user, session_id, job_id, env, resp, args, ctx, **kwargs):
        pass
