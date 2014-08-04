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


class AuthPluginBase(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def authenticate(self, user, password):
        pass

    @abc.abstractmethod
    def set_context(self, context):
        pass

    @abc.abstractmethod
    def validate(self, user, token):
        pass

    @abc.abstractmethod
    def create_token(self, user, password, **kwargs):
        pass

    @abc.abstractmethod
    def delete_token(self, user, token, **kwargs):
        pass

    @abc.abstractmethod
    def list_users(self, org, **kwargs):
        pass

    @abc.abstractmethod
    def list_orgs(self, **kwargs):
        pass

    @abc.abstractmethod
    def user_roles(self, username):
        pass

    @abc.abstractmethod
    def create_user(self, username, password, email, org_name=None):
        pass

    @abc.abstractmethod
    def update_user(self, username, password=None, email=None):
        pass

    @abc.abstractmethod
    def create_org(self, orgname):
        pass

    @abc.abstractmethod
    def activate_org(self, orgname):
        pass

    @abc.abstractmethod
    def deactivate_org(self, orgname):
        pass

    @abc.abstractmethod
    def remove_org(self, username):
        pass

    @abc.abstractmethod
    def remove_user(self, username):
        pass

    @abc.abstractmethod
    def add_role(self, username, node, role):
        pass

    @abc.abstractmethod
    def remove_role(self, username, node):
        pass


class NodeVerifier(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def verify(self, node, request, **kwargs):
        pass
