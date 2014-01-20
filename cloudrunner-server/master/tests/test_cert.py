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

from cloudrunner.tests import base
from cloudrunner.master.functions import CertController
from cloudrunner.master.functions import ConfigController
from cloudrunner.master.functions import ERR


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
        gen = CertController(base.CONFIG).create_ca('MyOrg')

    @classmethod
    def release_class(cls):
        if os.path.exists('/tmp/cloudrunner-tests/nodes'):
            shutil.rmtree('/tmp/cloudrunner-tests/nodes')
        if os.path.exists('/tmp/cloudrunner-tests/reqs'):
            shutil.rmtree('/tmp/cloudrunner-tests/reqs')
        if os.path.exists('/tmp/cloudrunner-tests/org'):
            shutil.rmtree('/tmp/cloudrunner-tests/org')

        base.CONFIG.update('Security', 'cert_pass', "")

    def test_sign(self):
        self._create_csr('TEST_NODE')
        gen = iter(CertController(base.CONFIG).list())
        next(gen)  # Pending nodes
        self.assertEqual(next(gen), (2, 'TEST_NODE'))
        next(gen)  # Approved nodes
        self.assertEqual(next(gen), (2, '--None--'))

        gen = iter(CertController(base.CONFIG).sign(['TEST_NODE'],
                                                    org="MyOrg"))
        self.assertEqual(next(gen), (1, 'Signing TEST_NODE'))
        self.assertEqual(next(gen), (1, 'Setting serial to 5'))
        self.assertEqual(next(gen), (2, 'TEST_NODE signed'))

        gen = iter(CertController(base.CONFIG).list())
        next(gen)  # Pending nodes
        self.assertEqual(next(gen), (2, '--None--'))
        next(gen)  # Approved nodes
        self.assertEqual(next(gen), (2, 'TEST_NODE'))

    def test_revoke(self):
        self._create_csr('TEST_NODE_2')
        self._create_csr('TEST_NODE_3')
        gen = iter(CertController(base.CONFIG).sign(['TEST_NODE_2'],
                                                    org='MyOrg'))
        self.assertEqual(next(gen), (1, 'Signing TEST_NODE_2'))
        self.assertEqual(next(gen), (1, 'Setting serial to 3'))
        self.assertEqual(next(gen), (2, 'TEST_NODE_2 signed'))
        gen = CertController(base.CONFIG).revoke(['TEST_NODE_2'])
        gen = iter(CertController(base.CONFIG).list())
        next(gen)  # Pending nodes
        self.assertEqual(next(gen), (2, 'TEST_NODE_3'))
        next(gen)  # Approved nodes
        self.assertEqual(next(gen), (2, '--None--'))

        gen = iter(CertController(base.CONFIG).sign(['TEST_NODE_3'],
                                                    org="MyOrg"))
        self.assertEqual(next(gen), (1, 'Signing TEST_NODE_3'))
        self.assertEqual(next(gen), (1, 'Setting serial to 4'))

        gen = CertController(base.CONFIG).revoke(['TEST_NODE_3'])

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

        req.sign(node_key, 'sha1')
        csr_file = os.path.join(os.path.dirname(base.CONFIG.security.ca),
                                'reqs',
                                '%s.csr' % node)
        req.save_pem(csr_file)
        del node_key
