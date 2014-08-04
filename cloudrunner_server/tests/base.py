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

import logging
import os
from unittest import TestCase

import cloudrunner.plugins as plugins
import cloudrunner_server.plugins as server_plugins
from cloudrunner.util.config import Config
from cloudrunner.util.loader import load_plugins

CONFIG = Config(os.path.join(os.path.dirname(__file__), 'test.config'))
LOG = logging.getLogger("BaseTest")

_plugins = [('common',
            os.path.join(os.path.dirname(plugins.__file__),
                         "state/functions.py")),
            ('signals',
            os.path.join(os.path.dirname(server_plugins.__file__),
                         "signals/signal_handler.py"))]

CONFIG.plugins.items = lambda: _plugins


class BaseTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        load_plugins(CONFIG)
        if hasattr(cls, 'fixture_class'):
            cls.fixture_class()
        if not hasattr(TestCase, 'assertIsNotNone'):
            def _assertIsNotNone(cls, val):
                cls.assertNotEqual(val, None)
            TestCase.assertIsNotNone = _assertIsNotNone
        if not hasattr(TestCase, 'assertIsNone'):
            def _assertIsNone(cls, val):
                cls.assertEqual(val, None)
            TestCase.assertIsNone = _assertIsNone

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'release_class'):
            cls.release_class()

    def setUp(self):

        if hasattr(self, 'fixture'):
            self.fixture()

    def tearDown(self):
        if hasattr(self, 'release'):
            self.release()

    @classmethod
    def _print(cls, msg):
        LOG.error(msg)

    def assertContains(self, where, what):
        self.assertTrue(what in where,
                        "[%s] not found in [%s] " % (what, where))

    def assertContainsNot(self, where, what):
        self.assertFalse(what in where,
                         "[%s] not found in [%s] " % (what, where))

    def assertType(self, obj, _type):
        self.assertTrue(isinstance(obj, _type), "(%s) %s is not %s" %
                        (obj, type(obj), _type))

    def assertCount(self, _list, count):
        self.assertEqual(len(_list), count)
