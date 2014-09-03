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

from datetime import datetime, timedelta
from mock import call, Mock, patch
import os
from pecan.testing import load_test_app
from pecan import conf, set_config
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from cloudrunner.util.crypto import hash_token
from cloudrunner_server.api.hooks.redis_hook import redis as r
from ...tests.base import BaseTestCase
from ..model import *  # noqa

engine = None
redis = Mock()
r.Redis = redis


class BaseRESTTestCase(BaseTestCase):

    @patch('redis.Redis', redis)
    def setUp(self):
        super(BaseRESTTestCase, self).setUp()
        self.app = load_test_app(os.path.join(
            os.path.dirname(__file__), '../../api',
            'config_test.py'
        ))
        self.redis = redis()
        incr = Mock()
        publ = Mock()
        self.redis.incr = incr
        self.redis.publish = publ

        self.redis.zrangebyscore.return_value = ['PREDEFINED_TOKEN']
        self.redis.hgetall.return_value = dict(uid=1, org='MyOrg')
        self.redis.smembers.return_value = {'role1', 'is_test_user',
                                            'is_admin'}
        self.redis.get.return_value = "10"
        self.populate()
        global engine
        conf.sqlalchemy.engine = engine

    def tearDown(self):
        super(BaseRESTTestCase, self).tearDown()
        set_config({}, overwrite=True)

    def populate(self):
        global engine
        engine = create_engine(
            'sqlite://',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool)
        Session.bind = engine
        metadata.bind = Session.bind

        # metadata.drop_all(Session.bind)
        metadata.create_all(Session.bind)

        # User data
        org = Org(name='MyOrg', active=True)
        Session.add(org)

        org2 = Org(name='MyOrg2', active=False)
        Session.add(org2)

        p1 = Permission(name='is_admin')
        Session.add(p1)

        user = User(username='testuser', email='email',
                    created_at=datetime(2014, 8, 1),
                    password=hash_token('testpassword'), org=org,
                    first_name="User", last_name="One", department="Dept",
                    position="Sr engineer")
        Session.add(user)
        Session.commit()

        user.permissions.append(p1)

        user2 = User(username='testuser2', email='email',
                     created_at=datetime(2014, 8, 2),
                     password=hash_token('testpassword'), org=org,
                     first_name="User", last_name="Second", department="HR",
                     position="HR manager")
        Session.add(user2)
        Session.commit()

        grp_admin = Group(name="admin", org=org)
        grp_admin.users.append(user2)
        Session.add(grp_admin)
        Session.commit()

        token = Token(value="PREDEFINED_TOKEN",
                      expires_at=datetime.now() + timedelta(minutes=60),
                      user_id=user.id,
                      scope='LOGIN')
        Session.add(token)
        Session.commit()

        role_admin = Role(group=grp_admin, servers='production',
                          as_user='root')
        Session.add(role_admin)
        role1 = Role(user_id=user.id,
                     servers="*", as_user='root')
        Session.add(role1)

        role2 = Role(user_id=user.id,
                     servers="prod.*", as_user='guest')
        Session.add(role2)

        role3 = Role(user_id=user.id,
                     servers="stg.*", as_user='developer')
        Session.add(role3)

        role2_1 = Role(user_id=user2.id,
                       servers="stg.*", as_user='developer')
        Session.add(role2_1)

        Session.commit()

        # Repository data
        repo1 = Repository(name='cloudrunner', owner=user)
        Session.add(repo1)
        repo11 = Repository(name='empty_repo', owner=user)
        Session.add(repo11)
        repo2 = Repository(name='private', owner=user2, private=True)
        Session.add(repo2)
        root1 = Folder(name="/", full_name="/", repository=repo1, owner=user)
        Session.add(root1)
        root11 = Folder(name="/", full_name="/", repository=repo11, owner=user)
        Session.add(root11)
        root2 = Folder(name="/", full_name="/", repository=repo2, owner=user)
        Session.add(root2)
        folder1 = Folder(name="/folder1", full_name="/folder1/",
                         repository=repo1, owner=user, parent=root1)
        Session.add(folder1)
        folder11 = Folder(name="/folder11", full_name="/folder1/folder11/",
                          repository=repo1, owner=user, parent=folder1)
        Session.add(folder11)
        folder2 = Folder(name="/folder2", full_name="/folder2/",
                         repository=repo2, owner=user, parent=root2)
        Session.add(folder2)
        folder21 = Folder(name="/folder11", full_name="/folder1/folder11/",
                          repository=repo2, owner=user, parent=folder2)
        Session.add(folder21)
        Session.commit()

        wf1 = Script(name='test1', folder=folder1, owner=user,
                     created_at=datetime(2014, 1, 10, 0, 0, 0),
                     content="hostname")
        Session.add(wf1)

        wf2 = Script(name='test2', folder=folder11, owner=user,
                     created_at=datetime(2014, 1, 20, 0, 0, 0),
                     mime_type="text/workflow",
                     content="#! switch [*]\ncloudrunner-node details")
        Session.add(wf2)

        wf3 = Script(name='test1', folder=folder2, owner=user2,
                     created_at=datetime(2014, 1, 30, 0, 0, 0),
                     content="cloudrunner-node details")
        Session.add(wf3)

        wf4 = Script(name='test2', folder=folder21, owner=user2,
                     created_at=datetime(2014, 1, 30, 0, 0, 0),
                     mime_type="text/template",
                     content="template 123")
        Session.add(wf4)

        Session.commit()

        log1 = Log(uuid='1111111111', owner=user, status=1,
                   created_at=datetime(2014, 8, 1), exit_code=-99)
        Session.add(log1)

        log2 = Log(uuid='2222222222', owner=user, status=2,
                   created_at=datetime(2014, 8, 2), exit_code=0)

        Session.add(log2)
        log2.tags.append(Tag(name="tag1"))
        log2.tags.append(Tag(name="tag2"))

        log3 = Log(uuid='3333333333', owner=user, status=2,
                   created_at=datetime(2014, 8, 3), exit_code=-1)

        Session.add(log3)
        step1 = Step(target="*", timeout=90, script="script")
        log3.steps.append(step1)

        step2 = Step(target="nodeX nodeY", timeout=90, script="script")
        log3.steps.append(step2)

        Session.commit()

        job1 = Job(name="trigger1", enabled=True, source=1,
                   arguments="* * * * *", target_id=1, owner_id=1)
        Session.add(job1)
        job2 = Job(name="trigger2", enabled=True, source=2, arguments="JOB",
                   target_id=3, owner_id=2)
        Session.add(job2)
        Session.commit()

    def assertRedisInc(self, value):
        if value:
            self.assertEqual(self.redis.incr.call_args_list,
                             [call(value)])
        else:
            self.assertEqual(self.redis.incr.call_args_list, [])

    def assertRedisPub(self, value, action):
        if value:
            self.assertEqual(self.redis.publish.call_args_list,
                             [call(value, action)])
        else:
            self.assertEqual(self.redis.publish.call_args_list, [])
