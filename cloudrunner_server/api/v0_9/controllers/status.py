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

import re
from pecan import expose, request, response
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.redis_hook import RedisHook
from cloudrunner_server.util.cache import CacheRegistry

MAX_TIMEOUT = 15


class Status(object):

    def __init__(self, retry_after=None, last_event_id=None, event=None):
        self.retry = retry_after
        self._event = ""
        self._data = []
        self.last_event_id = None
        if last_event_id:
            try:
                self.last_event_id = last_event_id
            except ValueError:
                self.last_event_id = None
        if event:
            self._event = event

    @classmethod
    def from_request(cls, request):
        return Status(last_event_id=request.headers.get("Last-Event-Id"))

    @property
    def data(self):
        return "\n".join(self._data)

    def add_line(self, target, value, event_id=None, retry=None):
        if event_id:
            self._data.append("id: %s" % event_id)
        if retry:
            self._data.append("retry: %s" % retry)
        self._data.append("event: %s" % target)
        self._data.append("data: %s" % value)
        self._data.append("")
        self._data.append("")

    def __iter__(self):
        return iter(self.data)


class EntityStatus(HookController):

    __hooks__ = [ErrorHook(), RedisHook()]

    @expose(content_type="text/event-stream")
    @expose(content_type="application/json")
    def get(self, org=None, *args, **kwargs):
        targets = kwargs.keys()

        cache = CacheRegistry(redis=request.redis)

        st = Status.from_request(request)

        for target in targets:
            if target == "logs":
                etag = cache.check(org, target)
                st.add_line(target, target, etag)
            else:
                tokens = target.split('_', 1)
                if len(tokens) == 1:
                    etag = cache.check(org, target)
                    st.add_line(target, target, etag, retry=1000)
                elif tokens[0] == 'tags':
                    data = tokens[1]
                    tags = sorted(re.split('[\s;,]', data))
                    etag = cache.check_group(org, *tags)
                    st.add_line(target, ','.join(tags), etag)

        resp = unicode(st.data)
        if resp:
            response.text = unicode(st.data)
        else:
            response.text = unicode("data: \n\n")
        response.content_type = "text/event-stream"
        response.cache_control = "no-cache"
        response.connection = "keep-alive"
        return response
