from pecan import conf
from pecan.hooks import PecanHook
from cloudrunner_server.api.model import Session


class UserHook(PecanHook):

    priority = 1

    def before(self, state):
        state.request.user_manager = conf.auth_manager
        state.request.user_manager.set_context(Session)
