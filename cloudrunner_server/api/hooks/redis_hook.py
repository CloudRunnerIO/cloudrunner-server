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

from pecan import conf, request  # noqa
from pecan.hooks import PecanHook
import redis


class RedisHook(PecanHook):

    priority = 99

    def before(self, state):
        r_server, r_port = conf.redis['host'], conf.redis['port']
        request.redis = redis.Redis(host=r_server, port=int(r_port), db=0)
