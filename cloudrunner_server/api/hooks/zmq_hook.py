from pecan.hooks import PecanHook

from cloudrunner_server.api.server import Master


class ZmqHook(PecanHook):

    priority = 101

    def before(self, state):
        user = state.request.headers.get('Cr-User')
        token = state.request.headers.get('Cr-Token')

        def zmq(user, token):
            def wrapper(*args, **kwargs):
                return Master(user, token).command(*args, **kwargs)
            return wrapper

        state.request.zmq = zmq(user, token)

        def reset(user, token):
            state.request.zmq = zmq(user, token)

        state.request.reset_zmq = reset

    def after(self, state):
        return
        if hasattr(state.request, 'zmq'):
            state.request.zmq.close()

    def on_error(self, state, exc):
        return
        if hasattr(state.request, 'zmq'):
            state.request.zmq.close()
