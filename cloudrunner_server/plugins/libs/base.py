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


class IncludeLibPluginBase(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def process(self, user, section, env, args):
        pass

    @abc.abstractmethod
    def add(self, user, name, script, **kwargs):
        pass

    @abc.abstractmethod
    def show(self, user, name, **kwargs):
        pass

    @abc.abstractmethod
    def list(self, user, **kwargs):
        pass

    @abc.abstractmethod
    def delete(self, user, name, **kwargs):
        pass
