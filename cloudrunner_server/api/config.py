from cloudrunner import CONFIG_LOCATION
from cloudrunner.util.config import Config
from cloudrunner.util.loader import local_plugin_loader
from cloudrunner.util.loader import load_plugins
import cloudrunner_server.api
from cloudrunner_server.api import VERSION
from cloudrunner_server.api import model
from pecan.hooks import RequestViewerHook, TransactionHook
from cloudrunner_server.api.base import SseRenderer, LibraryRenderer
from cloudrunner_server.plugins import PLUGIN_BASES
from cloudrunner_server.plugins.signals import signal_handler

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

auth_manager = local_plugin_loader(cr_config.auth)(cr_config)
schedule_manager = local_plugin_loader(cr_config.scheduler)()
loaded_plugins = load_plugins(cr_config)
signal_manager = None

for plugin_base in PLUGIN_BASES:
    for plugin in plugin_base.__subclasses__():
        if plugin == signal_handler.SignalHandlerPlugin:
            signal_manager = plugin()

redis = {
    'host': 'localhost',
    'port': 6379
}

zmq = {
    'server_uri': "ipc:///home/ttrifonov/.cloudrunner/"
    "var/run/sock/cloudrunner//local-api.sock"
}

sqlalchemy = {
    'url': 'mysql+pymysql://root:5b3dffd42a738a7e6998@localhost/' +
           'cloudrunner-server?charset=utf8&use_unicode=0',
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
        'py.warnings': {'handlers': ['console']},
        '__force_dict__': True
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'color'
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
