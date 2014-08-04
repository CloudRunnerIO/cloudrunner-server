from cloudrunner_server.tests.base import CONFIG
from cloudrunner.util.loader import local_plugin_loader
from cloudrunner.util.loader import load_plugins
import cloudrunner_server.api
from cloudrunner_server.api import VERSION
from cloudrunner_server.api import model
from pecan.hooks import TransactionHook
from cloudrunner_server.api.base import SseRenderer
from cloudrunner_server.plugins import PLUGIN_BASES
from cloudrunner_server.plugins.signals import signal_handler

DEBUG = False
# DEBUG = True

# Server Specific Configurations
server = {
    'port': '5558',
    'host': '0.0.0.0'
}

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
auth_manager = local_plugin_loader(CONFIG.auth)(CONFIG)
schedule_manager = local_plugin_loader(CONFIG.scheduler)()
loaded_plugins = load_plugins(CONFIG)
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
    'url': CONFIG.users.db,
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
