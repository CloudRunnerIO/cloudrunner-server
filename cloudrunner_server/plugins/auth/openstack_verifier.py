import M2Crypto as m
from keystoneclient.v2_0 import client as k
from novaclient.v1_1 import client as n
from novaclient import exceptions as novaexceptions

from cloudrunner_server.plugins.auth.base import NodeVerifier


class OpenStackVerifier(NodeVerifier):

    def __init__(self, config):
        self.config = config

        self.ADMIN_AUTH_URL = config.auth_admin_url
        self.admin_user = config.auth_user
        self.admin_pass = config.auth_pass
        self.admin_tenant = config.auth_admin_tenant or 'admin'
        self.strict_check = config.auth_strict_check
        self.timeout = int(config.auth_timeout or 5)

    def _get_token(self):
        try:
            keystone = k.Client(tenant_name=self.admin_tenant,
                                username=self.admin_user,
                                password=self.admin_pass,
                                auth_url=self.ADMIN_AUTH_URL,
                                timeout=self.timeout)

            token = keystone.tokens.authenticate(username=self.admin_user,
                                                 password=self.admin_pass)
            return token.id
        except Exception, e:
            print "ERRR", e
        return ""

    def verify(self, node, request, **kwargs):
        try:
            CN = request.get_subject().CN
            OU = request.get_subject().OU

            keystone = k.Client(token=self._get_token(),
                                auth_url=self.ADMIN_AUTH_URL,
                                tenant_name=self.admin_tenant,
                                timeout=self.timeout)

            tenants = keystone.tenants.list()

            conn = n.Client(self.admin_user, self.admin_pass,
                            self.admin_tenant, self.ADMIN_AUTH_URL,
                            service_type="compute",
                            timeout=self.timeout)

            for server in conn.servers.list(True,
                                            search_opts={'all_tenants': True}):
                if self.strict_check:
                    # Perform strict check by hostname and ID
                    if server.name != CN:
                        continue
                if server.id == OU:
                    tenant = filter(
                        lambda t: t.id == server.tenant_id, tenants)
                    if tenant:
                        return tenant[0].name
        except Exception, e:
            print "Verification error", e
            return None

        return None
