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

__author__ = 'Ivelin Slavov'

class Column(object):

    def __init__(self, col_type, primary_key=False, null=True,
                 autoincrement=False, default=None, **kwargs):
        self.col_type = col_type
        self.kwargs = kwargs
        self.primary_key = primary_key
        self.null = null
        self.autoincrement = autoincrement
        self.default = default

    def __str__(self):
        return self.col_type