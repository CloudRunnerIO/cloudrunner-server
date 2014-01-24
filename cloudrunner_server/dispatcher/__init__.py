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

ADMIN_TOWER = 'cloudrunner-control'


def is_valid_host(host):
    if not host:
        return False
    return not filter(lambda x: x.lower() == host.lower(),
                     (ADMIN_TOWER.lower(),))

SCHEDULER_URI_TEMPLATE = "ipc://%(sock_dir)s/scheduler.sock"


class PluginContext(object):

    def __init__(self, auth):
        self.props = {}
        self.auth = auth

    def __setattr__(self, name, prop):
        if name != 'props':
            self.props[name] = prop
        super(PluginContext, self).__setattr__(name, prop)

    def instance(self, user_id, password):
        ctx = PluginContext(self.auth)
        ctx.user_id = user_id
        ctx.password = password
        for name, prop in self.props.items():
            setattr(ctx, name, prop)
        return ctx

    def create_auth_token(self, expiry):
        return self.auth.create_token(self.user_id, self.password, expiry)


class Promise(object):

    def __init__(self, session_id):
        self.session_id = session_id
        self.main = False
        self.targets = []
        self.peer = None
        self.release = lambda: None
        self.owner = None
        self.remove = False

    def __str__(self):
        return "[%s] (%s) /%s /%s" % (self.session_id, self.main,
                                      self.peer, self.owner)

    def __repr__(self):
        return "[%s] (%s) /%s /%s" % (self.session_id, self.main,
                                      self.peer, self.owner)
