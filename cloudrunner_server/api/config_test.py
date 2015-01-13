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

from cloudrunner_server.tests.base import CONFIG
from cloudrunner.util.loader import local_plugin_loader
from cloudrunner.util.loader import load_plugins
import cloudrunner_server.api
from cloudrunner_server.api import VERSION
from cloudrunner_server.api import model
from pecan.hooks import TransactionHook
from cloudrunner_server.api.base import SseRenderer

DEBUG = False
# DEBUG = True

# Server Specific Configurations
server = {
    'port': '5558',
    'host': '0.0.0.0'
}

REST_SERVER_URL = "https://localhost/rest/"

APP_DIR = cloudrunner_server.api.__path__[0]

API_VER = VERSION.replace('.', '_')

# Pecan Application Configurations
app = {
    'root': 'cloudrunner_server.api.v%s.controllers.main.Main' % API_VER,
    'modules': ['cloudrunner_server.api'],
    'template_path': '%s/templates/rest/' % APP_DIR,
    'custom_renderers': {
        'sse': SseRenderer,
    },
    'debug': DEBUG,
    'errors': {
        '__force_dict__': True
    }
}

cr_config = CONFIG

schedule_manager = local_plugin_loader(CONFIG.scheduler)()
loaded_plugins = load_plugins(CONFIG)

zmq = {
    'server_uri': "ipc:///home/ttrifonov/.cloudrunner/"
    "var/run/sock/cloudrunner//local-api.sock"
}

sqlalchemy = {
    'echo': False,
    'echo_pool': False,
    'pool_recycle': 3600,
    'encoding': 'utf-8'
}

app['hooks'] = [
    TransactionHook(
        model.start,
        model.start,
        model.commit,
        model.rollback,
        model.clear
    )
]
