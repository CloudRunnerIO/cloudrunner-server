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

import abc
from hashlib import md5
import time

from cloudrunner.plugins.transport.base import TransportBackend


class ServerTransportBackend(TransportBackend):

    @abc.abstractmethod
    def prepare(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def terminate(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def create_fanout(self, endpoint, *args, **kwargs):
        raise NotImplementedError()

    @abc.abstractmethod
    def subscribe_fanout(self, endpoint, *args, **kwargs):
        raise NotImplementedError()

    @abc.abstractmethod
    def verify_node_request(self, node, request):
        raise NotImplementedError()


class Node(object):

    def __init__(self, name):
        self.created = time.time()
        self.name = name

    @property
    def last_seen(self):
        return time.time() - self.created

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

    def __delitem__(self, node_id):
        if node_id in self.nodes:
            self.nodes.remove(node_id)

    def __repr__(self):
        _repr = '[%s]\n' % self.id
        for node in self.nodes:
            _repr = "%s%s\tLast seen: %.f sec ago\n" % (_repr, node.name,
                                                        node.last_seen)
        return _repr

    def __eq__(self, _id):
        return self.id == _id

    def push(self, node):
        if node not in self.nodes:
            self.nodes.append(Node(node))
        else:
            self.nodes[self.nodes.index(node)].created = time.time()
