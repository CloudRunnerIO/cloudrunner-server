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

from . import base, sql, helpers
from .columns import Column

dal_register = {}

def get_db(dburl):
    db_args = helpers.parse_dburl(dburl)
    if dburl not in dal_register:
        dal_register[dburl] = base.database(**db_args)
    cur_db = dal_register[dburl]
    return sql.SQLDatabase(cur_db)
