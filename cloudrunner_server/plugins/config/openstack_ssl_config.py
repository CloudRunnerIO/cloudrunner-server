import json
import httplib
import logging
import M2Crypto as m
import os
import random
from socket import gethostname
import stat
from string import ascii_letters

from cloudrunner.plugins.config.base import ConfigPluginBase
from cloudrunner import LIB_DIR

LOG = logging.getLogger(__name__)


class SslConfig(ConfigPluginBase):

    def __init__(self, config, **kwargs):
        self.config = config
        self.conf_dir = os.path.join(kwargs.get('var_dir', None) or LIB_DIR,
                                     "cloudrunner_node")
        self.key_size = int(config.security.key_size or 2048,)

    def create_config(self, node_id, overwrite=False, **kwargs):
        self.cert_dir = os.path.join(self.conf_dir, 'certs')
        if not os.path.exists(self.cert_dir):
            os.makedirs(self.cert_dir)

        key_file = self.config.security.node_key
        if os.path.exists(key_file):
            if not overwrite:
                print ("Node key file already exists in your config. "
                       "If you want to create new one - run\n"
                       "\tcloudrunner-node configure --overwrite\n"
                       "IMPORTANT! Please note that regenerating your key "
                       "and certificate will prevent the node from "
                       "connecting to the Master, if it already has "
                       "an approved certificate!")
                return False

        crt_file = self.config.security.node_cert
        if os.path.exists(crt_file):
            if not overwrite:
                print ("Node certificate file already exists in your config. "
                       "If you still want to create new one - run\n"
                       "\tcloudrunner-node configure --overwrite\n"
                       "IMPORTANT! Please note that regenerating your key "
                       "and certificate will prevent the node from "
                       "connecting to the Master, if it already has "
                       "an approved certificate!")
                return False

        cert_password = ''.join([random.choice(ascii_letters)
                                 for x in range(32)])

        key_file = os.path.join(self.cert_dir, '%s.key' % node_id)
        csr_file = os.path.join(self.cert_dir, '%s.csr' % node_id)
        crt_file = os.path.join(self.cert_dir, '%s.crt' % node_id)

        node_key = m.EVP.PKey()

        rsa = m.RSA.gen_key(self.key_size, 65537, lambda: True)
        node_key.assign_rsa(rsa)
        rsa = None

        print ("Saving KEY file %s" % key_file)
        node_key.save_key(key_file, callback=lambda x: cert_password)
        os.chmod(key_file, stat.S_IREAD | stat.S_IWRITE)

        req = m.X509.Request()
        req.set_pubkey(node_key)
        req.set_version(2)

        subj = req.get_subject()

        try:
            import locale
            l_c = locale.getdefaultlocale()
            subj.C = l_c[0].rpartition('_')[-1]
        except:
            pass
        if not subj.C or len(subj.C) != 2:
            subj.C = "US"

        subj.CN = node_id
        subj.OU = self.get_meta_data('uuid')

        req.sign(node_key, 'sha1')
        assert req.verify(node_key)
        assert req.verify(req.get_pubkey())

        print ("Saving CSR file %s" % csr_file)
        req.save_pem(csr_file)
        os.chmod(csr_file, stat.S_IREAD | stat.S_IWRITE)

        print ('Generation of credentials is complete.'
               'Now run cloudrunner-node to register at Master')

        if os.path.exists(crt_file):
            # if crt file exists - remove it, as it cannot be used
            # anymore with the key file
            os.unlink(crt_file)
        print ("Updating config settings")
        self.config.update('General', 'work_dir',
                           os.path.join(self.conf_dir, 'tmp'))
        self.config.update('Security', 'cert_path', self.cert_dir)
        self.config.update('Security', 'node_key', key_file)
        self.config.update('Security', 'node_csr', csr_file)
        self.config.update('Security', 'node_cert', crt_file)
        self.config.update('Security', 'cert_pass', cert_password)
        self.config.update('Security', 'ca', '')
        self.config.update('Security', 'server', '')
        self.config.reload()

    def get_meta_data(self, key):
        address = '169.254.169.254'
        conn = httplib.HTTPConnection(address)
        path = '/openstack/2013-04-04/meta_data.json'
        try:
            conn.request('GET', path)
            res = conn.getresponse()
            if res.status != 200:
                LOG.error("ERROR: Cannot load metadata at %s" % address)
            else:
                return json.loads(res.read()).get(key, '')
        except Exception, ex:
            LOG.error("Cannot load metadata: %s" % ex)
            return ""
