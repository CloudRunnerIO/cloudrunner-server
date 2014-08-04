from pecan.hooks import PecanHook

from cloudrunner_server.api.server import Master


class ZmqHook(PecanHook):

    priority = 101

    def before(self, state):
        user = state.request.headers.get('Cr-User')
        token = state.request.headers.get('Cr-Token')
        if user and token:
            state.request.zmq = lambda *args, **kwargs: Master(
                user,
                token).command(*args, **kwargs)

    def after(self, state):
        return
        if hasattr(state.request, 'zmq'):
            state.request.zmq.close()

    def on_error(self, state, exc):
        return
        if hasattr(state.request, 'zmq'):
            state.request.zmq.close()
