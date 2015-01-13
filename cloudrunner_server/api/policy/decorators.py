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

import logging
from functools import wraps  # noqa
from pecan import request, abort

LOG = logging.getLogger()


def check_policy(*args):
    permissions = set(args)

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Call function
            if not set(request.user.permissions).intersection(permissions):
                abort(401)

            return f(*args, **kwargs)
        return wrapper

    return decorator
