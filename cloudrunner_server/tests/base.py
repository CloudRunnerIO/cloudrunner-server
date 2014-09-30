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
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import cloudrunner.plugins as plugins
from cloudrunner.util.config import Config
from cloudrunner.util.loader import load_plugins
from cloudrunner_server.api.model import *  # noqa

CONFIG = Config(os.path.join(os.path.dirname(__file__), 'test.config'))
LOG = logging.getLogger("BaseTest")

_plugins = [('common',
            os.path.join(os.path.dirname(plugins.__file__),
                         "state/functions.py")),
            # ('signals', "cloudrunner_server.plugins.signals.signal_handler")]
            ]
CONFIG.plugins.items = lambda: _plugins
engine = None


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


class BaseDBTestCase(BaseTestCase):

    @classmethod
    def fixture_class(cls):
        global engine
        engine = create_engine(
            'sqlite://',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool)
        Session.bind = engine
        metadata.bind = Session.bind
        cls.ENGINE = engine
        # metadata.drop_all(Session.bind)
        metadata.create_all(Session.bind)

    def setUp(self):
        super(BaseDBTestCase, self).setUp()

    def tearDown(self):
        super(BaseDBTestCase, self).tearDown()
