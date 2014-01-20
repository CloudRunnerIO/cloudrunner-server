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


class StorePluginBase(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def save(self, user, response):
        raise NotImplementedError()

    @abc.abstractmethod
    def list(self, user, **kwargs):
        raise NotImplementedError()

    @abc.abstractmethod
    def search(self, user, **kwargs):
        raise NotImplementedError()
