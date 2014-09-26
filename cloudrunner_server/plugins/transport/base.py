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

import abc
from hashlib import md5
import logging
import time

from cloudrunner.plugins.transport.base import TransportBackend

LOG = logging.getLogger()


class ServerTransportBackend(TransportBackend):

    @abc.abstractmethod
    def prepare(self):
        pass

    @abc.abstractmethod
    def register_session(self, session_id):
        pass

    @abc.abstractmethod
    def unregister_session(self, session_id):
        pass

    @abc.abstractmethod
    def terminate(self):
        pass

    @abc.abstractmethod
    def create_fanout(self, endpoint, *args, **kwargs):
        pass

    @abc.abstractmethod
    def subscribe_fanout(self, endpoint, sub_pattern=None, *args, **kwargs):
        pass


class Node(object):

    def __init__(self, name):
        self.refreshed = time.time()
        self.name = name
        self.usage = {}

    @property
    def last_seen(self):
        return time.time() - self.refreshed

    def __eq__(self, name):
        return self.name == name


class Tenant(object):

    def __init__(self, name):
        self.name = str(name)
        m = md5()
        m.update(name)
        self.id = str(m.hexdigest())
        del m
        self.nodes = []
        self.refresh()

    def __delitem__(self, node_id):
        if node_id in self.nodes:
            self.nodes.remove(node_id)

    def __repr__(self):
        _repr = '[%s] [%.f sec ago]\n' % (
            self.id, time.time() - self.refreshed)
        for node in self.nodes:
            _repr = "%s%s\tLast seen: %.f sec ago\n" % (_repr, node.name,
                                                        node.last_seen)
        return _repr

    def __eq__(self, _id):
        return self.id == _id

    def push(self, node):
        new_node = False
        if node not in self.nodes:
            self.nodes.append(Node(node))
            new_node = True
        self.nodes[self.nodes.index(node)].refreshed = time.time()
        return new_node

    def pop(self, node):
        if node in self.nodes:
            self.nodes.remove(Node(node))

    def refresh(self, adjust=0):
        self.refreshed = time.time() + adjust

    def update(self, node, usage):
        self.nodes[self.nodes.index(node)].usage = usage

    def active_nodes(self):
        return [node for node in self.nodes if node.refreshed > self.refreshed]


class TenantDict(dict):

    def __init__(self, refresh=None, *args, **kwargs):
        super(TenantDict, self).__init__(*args, **kwargs)
        self.refresh = refresh

    def __getitem__(self, key):
        try:
            return super(TenantDict, self).__getitem__(key)
        except KeyError:
            LOG.warn("Hit miss from tenants for %s, trying refresh" % key)
            self.refresh()
            return super(TenantDict, self).__getitem__(key)
