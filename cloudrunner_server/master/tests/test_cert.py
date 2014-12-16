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

import os
import M2Crypto as m
import shutil

from cloudrunner_server.tests import base
from cloudrunner_server.master.functions import CertController
from cloudrunner_server.master.functions import ConfigController
from cloudrunner_server.master.functions import ERR


class TestCert(base.BaseDBTestCase):

    @classmethod
    def fixture_class(cls):
        super(TestCert, cls).fixture_class()
        ccont = CertController(base.CONFIG, engine=cls.ENGINE)
        assert base.CONFIG.security.ca == '/tmp/cloudrunner-tests/ca.crt'
        base.CONFIG.security.auto_approve = True
        conf_ctrl = ConfigController(base.CONFIG)
        gen = conf_ctrl.create(overwrite=True)
        for line in gen:
            assert line[0] != ERR, line
        if os.path.exists('/tmp/cloudrunner-tests/org'):
            shutil.rmtree('/tmp/cloudrunner-tests/org')
        print ccont.create_ca('DEFAULT')

    @classmethod
    def release_class(cls):
        if os.path.exists('/tmp/cloudrunner-tests/nodes'):
            shutil.rmtree('/tmp/cloudrunner-tests/nodes')
        if os.path.exists('/tmp/cloudrunner-tests/reqs'):
            shutil.rmtree('/tmp/cloudrunner-tests/reqs')
        if os.path.exists('/tmp/cloudrunner-tests/org'):
            shutil.rmtree('/tmp/cloudrunner-tests/org')
        if os.path.exists('/tmp/cloudrunner-tests/issued'):
            shutil.rmtree('/tmp/cloudrunner-tests/issued')

        base.CONFIG.update('Security', 'cert_pass', "")

    def test_sign_revoke(self):
        self._create_csr('TEST_NODE')
        messages = [x for x in CertController(base.CONFIG).list()]

        self.assertEqual(messages.pop(0), (1, 'Pending node requests:'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE'))
        self.assertEqual(messages.pop(0), (1, 'Approved nodes:'))
        self.assertEqual(messages.pop(0), (2, '--None--'))
        self.assertEqual(messages, [])

        messages = [x for x in CertController(base.CONFIG).sign(['TEST_NODE'])]
        self.assertEqual(messages.pop(0), (1, 'Signing TEST_NODE'))
        self.assertEqual(messages.pop(0), (1, 'Setting serial to 3'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE signed'))

        messages = [x for x in CertController(base.CONFIG).list()]
        print messages

        self.assertEqual(messages.pop(0), (1, 'Pending node requests:'))
        self.assertEqual(messages.pop(0), (2, '--None--'))
        self.assertEqual(messages.pop(0), (1, 'Approved nodes:'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE'))
        self.assertEqual(messages, [])

        self._create_csr('TEST_NODE_2')
        self._create_csr('TEST_NODE_PEND')
        messages = [x for x in CertController(
            base.CONFIG).sign(['TEST_NODE_2'])]

        self.assertEqual(messages.pop(0), (1, 'Signing TEST_NODE_2'))
        self.assertEqual(messages.pop(0), (1, 'Setting serial to 4'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE_2 signed'))

        messages = [x for x in CertController(base.CONFIG).revoke(
            ['TEST_NODE_2'])]
        messages = [x for x in CertController(base.CONFIG).list()]

        self.assertEqual(messages.pop(0), (1, 'Pending node requests:'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE_PEND'))
        self.assertEqual(messages.pop(0), (1, 'Approved nodes:'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE'))
        self.assertEqual(messages, [])

        CertController(base.CONFIG).revoke(['TEST_NODE_2'])

        messages = [x for x in CertController(base.CONFIG).list()]

        self.assertEqual(messages.pop(0), (1, 'Pending node requests:'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE_PEND'))
        self.assertEqual(messages.pop(0), (1, 'Approved nodes:'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE'))
        self.assertEqual(messages, [])

        messages = [x for x in CertController(base.CONFIG).sign(
            ['TEST_NODE_PEND'],
            org="DEFAULT")]

        self.assertEqual(messages.pop(0), (1, 'Signing TEST_NODE_PEND'))
        self.assertEqual(messages.pop(0), (1, 'Setting serial to 5'))

        messages = [x for x in CertController(base.CONFIG).list()]

        self.assertEqual(messages.pop(0), (1, 'Pending node requests:'))
        self.assertEqual(messages.pop(0), (2, '--None--'))
        self.assertEqual(messages.pop(0), (1, 'Approved nodes:'))
        nodes = [messages.pop(0), messages.pop(0)]
        self.assertEqual(sorted(nodes),
                         sorted([(2, 'TEST_NODE_PEND'), (2, 'TEST_NODE')]))
        self.assertEqual(messages, [])

        self._create_csr('INVALID NAME')
        messages = [x for x in CertController(base.CONFIG).sign(
            ['INVALID NAME'],
            org="DEFAULT")]

        self.assertEqual(messages.pop(0), (3, 'Invalid node name'))
        self.assertEqual(messages, [])

        self._create_csr('INVALID_NAME#2')
        messages = [x for x in CertController(base.CONFIG).sign(
            ['INVALID_NAME#2'],
            org="DEFAULT")]

        self.assertEqual(messages.pop(0), (3, 'Invalid node name'))
        self.assertEqual(messages, [])

        self._create_csr('VALID_NAME.DOMAIN')
        messages = [x for x in CertController(base.CONFIG).sign(
            ['VALID_NAME.DOMAIN'],
            org="DEFAULT")]

        self.assertEqual(messages.pop(0), (1, 'Signing VALID_NAME.DOMAIN'))
        self.assertEqual(messages.pop(0), (1, 'Setting serial to 6'))
        self.assertEqual(messages.pop(0), (2, 'VALID_NAME.DOMAIN signed'))
        self.assertEqual(
            messages.pop(0), (2, 'Issuer /C=%s/O=DEFAULT/CN=DEFAULT' %
                              self.country))
        self.assertEqual(
            messages.pop(0),
            (2, 'Subject /C=%s/CN=VALID_NAME.DOMAIN/O=DEFAULT' % self.country))
        self.assertEqual(messages, [])

    @property
    def country(self):
        try:
            import locale
            l_c = locale.getdefaultlocale()
            country = l_c[0].rpartition('_')[-1]
        except:
            country = "US"
        return country

    def _create_csr(self, node):
        node_key = m.EVP.PKey()

        rsa = m.RSA.gen_key(2048, 65537, lambda: True)
        node_key.assign_rsa(rsa)
        del rsa

        req = m.X509.Request()
        req.set_pubkey(node_key)
        req.set_version(2)

        subj = req.get_subject()
        subj.C = self.country
        subj.CN = node
        subj.OU = 'DEFAULT'

        req.sign(node_key, 'sha1')
        csr_file = os.path.join(os.path.dirname(base.CONFIG.security.ca),
                                'reqs',
                                'DEFAULT.%s.csr' % node)
        req.save_pem(csr_file)
        del node_key
