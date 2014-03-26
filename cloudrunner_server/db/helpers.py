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

from urlparse import urlparse


def parse_dburl(dburl):
    '''
    Parses a db url to dictionary. Available keys are
        res = {
            'dbn': None,
            'driver': None,
            'db': None,
            'user': None,
            'pw': None,
            'host': None,
            'port': None,
        }
    '''
    res = {}
    parsed = urlparse(dburl)
    if "+" in parsed.scheme:
        res['dbn'], res['driver'] = parsed.scheme.split("+", 1)
    else:
        res['dbn'] = parsed.scheme
    if parsed.username:
        res['user'] = parsed.username
    if parsed.password:
        res['pw'] = parsed.password
    if parsed.hostname:
        res['host'] = parsed.hostname
    if parsed.port:
        res['port'] = parsed.port
    db_path = parsed.path
    if parsed.netloc:
        db_path = parsed.path.lstrip('/')
    res['db'] = db_path
    return res
