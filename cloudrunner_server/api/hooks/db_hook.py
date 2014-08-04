from pecan.hooks import PecanHook
from cloudrunner_server.api.model import Session


class DbHook(PecanHook):

    priority = 2

    def before(self, state):
        state.request.db = Session

    def after(self, state):
        state.request.db.commit()

    def on_error(self, state, exc):
        state.request.db.rollback()
