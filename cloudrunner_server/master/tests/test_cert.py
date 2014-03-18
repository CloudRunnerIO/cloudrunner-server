#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 CloudRunner.IO
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import M2Crypto as m
import shutil

from cloudrunner_server.tests import base
from cloudrunner_server.master.functions import CertController
from cloudrunner_server.master.functions import ConfigController
from cloudrunner_server.master.functions import ERR


class TestCert(base.BaseTestCase):

    @classmethod
    def fixture_class(cls):
        assert base.CONFIG.security.ca == '/tmp/cloudrunner-tests/ca.crt'
        conf_ctrl = ConfigController(base.CONFIG)
        gen = conf_ctrl.create(overwrite=True)
        for line in gen:
            assert line[0] != ERR, line
        if os.path.exists('/tmp/cloudrunner-tests/org'):
            shutil.rmtree('/tmp/cloudrunner-tests/org')
        CertController(base.CONFIG).create_ca('MyOrg')

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

        messages = [x for x in CertController(base.CONFIG).sign(['TEST_NODE'],
                                                                org="MyOrg")]
        self.assertEqual(messages.pop(0), (1, 'Signing TEST_NODE'))
        self.assertEqual(messages.pop(0), (1, 'Setting serial to 3'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE signed'))

        messages = [x for x in CertController(base.CONFIG).list()]

        self.assertEqual(messages.pop(0), (1, 'Pending node requests:'))
        self.assertEqual(messages.pop(0), (2, '--None--'))
        self.assertEqual(messages.pop(0), (1, 'Approved nodes:'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE'))
        self.assertEqual(messages, [])

        self._create_csr('TEST_NODE_2')
        self._create_csr('TEST_NODE_PEND')
        messages = [x for x in CertController(
            base.CONFIG).sign(['TEST_NODE_2'],
                              org='MyOrg')]

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
            org="MyOrg")]

        self.assertEqual(messages.pop(0), (1, 'Signing TEST_NODE_PEND'))
        self.assertEqual(messages.pop(0), (1, 'Setting serial to 5'))

        messages = [x for x in CertController(base.CONFIG).list()]

        self.assertEqual(messages.pop(0), (1, 'Pending node requests:'))
        self.assertEqual(messages.pop(0), (2, '--None--'))
        self.assertEqual(messages.pop(0), (1, 'Approved nodes:'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE_PEND'))
        self.assertEqual(messages.pop(0), (2, 'TEST_NODE'))
        self.assertEqual(messages, [])

        self._create_csr('INVALID NAME')
        messages = [x for x in CertController(base.CONFIG).sign(
            ['INVALID NAME'],
            org="MyOrg")]

        self.assertEqual(messages.pop(0), (3, 'Invalid node name'))
        self.assertEqual(messages, [])

        self._create_csr('INVALID_NAME#2')
        messages = [x for x in CertController(base.CONFIG).sign(
            ['INVALID_NAME#2'],
            org="MyOrg")]

        self.assertEqual(messages.pop(0), (3, 'Invalid node name'))
        self.assertEqual(messages, [])

        self._create_csr('VALID_NAME.DOMAIN')
        messages = [x for x in CertController(base.CONFIG).sign(
            ['VALID_NAME.DOMAIN'],
            org="MyOrg")]

        self.assertEqual(messages.pop(0), (1, 'Signing VALID_NAME.DOMAIN'))
        self.assertEqual(messages.pop(0), (1, 'Setting serial to 6'))
        self.assertEqual(messages.pop(0), (2, 'VALID_NAME.DOMAIN signed'))
        self.assertEqual(
            messages.pop(0), (2, 'Issuer /C=US/CN=CloudRunner Master CA'))
        self.assertEqual(
            messages.pop(0), (2, 'Subject /C=US/CN=VALID_NAME.DOMAIN'))
        self.assertEqual(messages, [])

    def _create_csr(self, node):
        node_key = m.EVP.PKey()

        rsa = m.RSA.gen_key(2048, 65537, lambda: True)
        node_key.assign_rsa(rsa)
        del rsa

        req = m.X509.Request()
        req.set_pubkey(node_key)
        req.set_version(2)

        subj = req.get_subject()
        subj.C = "US"
        subj.CN = node
        subj.OU = 'DEFAULT'

        req.sign(node_key, 'sha1')
        csr_file = os.path.join(os.path.dirname(base.CONFIG.security.ca),
                                'reqs',
                                'DEFAULT.%s.csr' % node)
        req.save_pem(csr_file)
        del node_key
