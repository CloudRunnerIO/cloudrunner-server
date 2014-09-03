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

from cloudrunner.plugins import PLUGIN_BASES as _BASES
from cloudrunner_server.plugins.jobs.base import JobInOutProcessorPluginBase
from cloudrunner_server.plugins.libs.base import IncludeLibPluginBase

PLUGIN_BASES = tuple(list(_BASES) + [JobInOutProcessorPluginBase,
                                     IncludeLibPluginBase])
