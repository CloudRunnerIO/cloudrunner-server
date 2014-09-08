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
from cloudrunner.util.loader import local_plugin_loader
import cloudrunner_server.api
from cloudrunner_server.api import VERSION
from cloudrunner_server.api import model
from pecan.hooks import RequestViewerHook, TransactionHook
from cloudrunner_server.api.base import SseRenderer, LibraryRenderer

DEBUG = False
# DEBUG = True

REST_SERVER_URL = "http://dash:12000/rest/"

APP_DIR = cloudrunner_server.api.__path__[0]

API_VER = VERSION.replace('.', '_')

# Pecan Application Configurations
app = {
    'root': 'cloudrunner_server.api.v%s.controllers.main.Main' % API_VER,
    'modules': ['cloudrunner_server.api'],
    'template_path': '%s/templates/rest/' % APP_DIR,
    'custom_renderers': {
        'sse': SseRenderer,
        'library': LibraryRenderer
    },
    'debug': DEBUG,
    'errors': {
        '__force_dict__': True
    }
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

if DEBUG:
    app['hooks'].append(RequestViewerHook())
    app['static_root'] = '%s/templates/' % APP_DIR

cr_config = Config(CONFIG_LOCATION)

schedule_manager = local_plugin_loader(cr_config.scheduler)()

redis = {
    'host': 'localhost',
    'port': 6379
}

zmq = {
    'server_uri': "tcp://0.0.0.0:5559"
}

sqlalchemy = {
    'echo': False,
    'echo_pool': False,
    'pool_recycle': 3600,
    'encoding': 'utf-8'
}

logging = {
    'loggers': {
        'root': {'level': 'INFO', 'handlers': ['console']},
        'simpleapp': {'level': 'DEBUG', 'handlers': ['console']},
        'pecan.commands.serve': {'level': 'DEBUG', 'handlers': ['console']},
        'sqlalchemy.engine': {'level': 'WARN', 'handlers': ['db']},
        'py.warnings': {'handlers': ['console']},
        '__force_dict__': True
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'color'
        },
        'db': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        }
    },
    'formatters': {
        'simple': {
            'format': ('%(asctime)s %(levelname)-5.5s [%(name)s]'
                       '[%(threadName)s] %(message)s')
        },
        'color': {
            '()': 'pecan.log.ColorFormatter',
            'format': ('%(asctime)s [%(padded_color_levelname)s] [%(name)s]'
                       '[%(threadName)s] %(message)s'),
            '__force_dict__': True
        }
    }
}
