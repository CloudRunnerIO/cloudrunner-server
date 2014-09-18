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

import logging
from pecan import request, response
from mako.template import Template

from cloudrunner_server.api.model import Script
from cloudrunner_server.api.hooks.zmq_hook import ZmqHook

LOG = logging.getLogger()


class ZmqMixin(object):
    __hooks__ = [ZmqHook()]


class DbMixin(object):
    __hooks__ = []


class SseRenderer(object):

    def __init__(self, path, extra_vars):
        pass

    def render(self, template_path, res):
        _res = []
        if res.id:
            _res.append("id: %s" % res.id)
        if res.event:
            _res.append("event: %s" % res.event)
        _data = res.data
        if _data:
            _res.extend(res.data)

        return response  # "\n".join(_res)


class LibraryRenderer(object):

    def __init__(self, path, extra_vars):
        self.path = path

    def render(self, template_path, res):
        try:
            script = Script.find(request, template_path).first()
            if not script:
                return ("Template %s not found in the library" %
                        template_path)
        except Exception, ex:
            LOG.error(ex)
            request.db.rollback()
            return ("Template %s not found in the library" %
                    template_path)

        template = Template(script.contents(request).content)

        return template.render(**res)
