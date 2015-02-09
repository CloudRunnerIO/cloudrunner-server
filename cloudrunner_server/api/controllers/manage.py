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
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook

LOG = logging.getLogger()

from .groups import Groups
from .nodes import Nodes
from .orgs import Orgs
from .roles import Roles
from .users import Users


class Manage(HookController, Users, Roles, Groups, Nodes, Orgs):
    __hooks__ = [DbHook(), ErrorHook()]
