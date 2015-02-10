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

from cloudrunner import CONFIG_LOCATION
from cloudrunner.util.config import Config
from cloudrunner_server.tests.base import CONFIG
from cloudrunner.util.loader import local_plugin_loader
import cloudrunner_server.api
from cloudrunner_server.api import model
from pecan.hooks import TransactionHook
from cloudrunner_server.api.base import SseRenderer

DEBUG = False
# DEBUG = True

# Server Specific Configurations
cr_config = Config(CONFIG_LOCATION)

REST_SERVER_URL = "https://localhost/rest/"
DASH_SERVER_URL = cr_config.dash_api_url or "http://localhost/"

APP_DIR = cloudrunner_server.api.__path__[0]

# Pecan Application Configurations
app = {
    'root': 'cloudrunner_server.api.controllers.main.Main',
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

schedule_manager = local_plugin_loader(CONFIG.scheduler)()

zmq = {
    'server_uri': "ipc:///tmp/local-api.sock"
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
