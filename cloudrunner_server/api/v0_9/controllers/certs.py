from pecan import expose
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.util import JsonOutput as O


class Certs(HookController):

    __hooks__ = [DbHook(), ErrorHook(), SignalHook()]

    @expose('json', generic=True)
    def nodes(self, *args, **kwargs):

        if args:
            return O.nodes(_list=[])
        else:
            if 'approved' in args:
                return O.nodes(_list=[])
            elif 'pending' in args:
                return O.nodes(_list=[])

            return O.nodes(_list=[])

    @nodes.when(method='POST', template='json')
    @signal('cert.nodes', 'sign',
            when=lambda x: x.get("status") == "ok")
    def nodes_sign(self, **kwargs):

        return dict(status="ok")

    @nodes.when(method='DELETE', template='json')
    @signal('cert.nodes', 'revoke',
            when=lambda x: x.get("status") == "ok")
    def nodes_revoke(self, node, **kwargs):

        return dict(status="ok")

    @expose('json', generic=True)
    def ca(self, *args, **kwargs):

        if args:
            return O.ca({'name': 'CA1'})
        else:
            return O.ca(_list=[])

    @nodes.when(method='POST', template='json')
    @signal('cert.ca', 'create',
            when=lambda x: x.get("status") == "ok")
    def ca_create(self, *args, **kwargs):

        return dict(status='ok')

    @ca.when(method='DELETE', template='json')
    @signal('cert.ca', 'delete',
            when=lambda x: x.get("status") == "ok")
    def ca_delete(self, ca, *args, **kwargs):

        return dict(status='ok')
