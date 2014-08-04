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


class ArgsProvider(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def append_args(self, arg_parser):
        pass

BOOL = {'1': True, 'true': True, 'True': True,
        '0': False, 'false': False, 'False': False}


class ManagedPlugin(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def start(self):
        pass

    @abc.abstractmethod
    def stop(self):
        pass
