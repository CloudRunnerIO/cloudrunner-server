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


class AuthPluginBase(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def authenticate(self, user, password):
        raise NotImplementedError()

    @abc.abstractmethod
    def validate(self, user, token):
        raise NotImplementedError()

    @abc.abstractmethod
    def create_token(self, user, password, **kwargs):
        raise NotImplementedError()

    @abc.abstractmethod
    def list_users(self, **kwargs):
        raise NotImplementedError()

    @abc.abstractmethod
    def list_orgs(self, **kwargs):
        raise NotImplementedError()

    @abc.abstractmethod
    def user_roles(self, username):
        raise NotImplementedError()

    @abc.abstractmethod
    def create_user(self, username, password, org_name):
        raise NotImplementedError()

    @abc.abstractmethod
    def create_org(self, orgname):
        raise NotImplementedError()

    @abc.abstractmethod
    def activate_org(self, orgname):
        raise NotImplementedError()

    @abc.abstractmethod
    def deactivate_org(self, orgname):
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_org(self, username):
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_user(self, username):
        raise NotImplementedError()

    @abc.abstractmethod
    def add_role(self, username, node, role):
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_role(self, username, node):
        raise NotImplementedError()
