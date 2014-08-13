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

        user = User(username='testuser', email='email',
                    password=hash_token('testpassword'), org=org)
        Session.add(user)
        Session.commit()

        user2 = User(username='testuser2', email='email',
                     password=hash_token('testpassword'), org=org)
        Session.add(user2)
        Session.commit()

        grp_admin = Group(name="admin")
        grp_admin.users.append(user2)
        Session.add(grp_admin)
        Session.commit()

        token = Token(value="PREDEFINED_TOKEN",
                      expires_at=datetime.now() + timedelta(minutes=60),
                      user_id=user.id)
        Session.add(token)
        Session.commit()

        role1 = Role(name="default", user_id=user.id,
                     servers="*", as_user='root')
        Session.add(role1)

        role2 = Role(name="production", user_id=user.id,
                     servers="prod.*", as_user='guest')
        Session.add(role2)

        role3 = Role(name="staging", user_id=user.id,
                     servers="stg.*", as_user='developer')
        Session.add(role3)

        role2_1 = Role(name="default", user_id=user2.id,
                       servers="stg.*", as_user='developer')
        Session.add(role2_1)

        Session.commit()

        # Library data
        store = Store(name='cloudrunner', store_type='local')
        Session.add(store)
        Session.commit()

        wf1 = Workflow(name='test/wf1', store=store, owner=user,
                       created_at=datetime(2014, 1, 10, 0, 0, 0),
                       content="#! switch [*]\nhostname")
        Session.add(wf1)

        wf2 = Workflow(name='test/wf2', store=store, owner=user,
                       private=True,
                       created_at=datetime(2014, 1, 20, 0, 0, 0),
                       content="#! switch [*]\ncloudrunner-node details")
        Session.add(wf2)

        wf3 = Workflow(name='test/wf3', store=store, owner=user,
                       created_at=datetime(2014, 1, 30, 0, 0, 0),
                       content="#! switch [*]\ncloudrunner-node details")
        Session.add(wf3)

        inl1 = Inline(name='tools/ifconfig',
                      created_at=datetime(2014, 1, 10, 0, 0, 0),
                      content='/sbin/ifconfig', owner=user)
        Session.add(inl1)

        inl2 = Inline(name='tools/nginx_status',
                      private=True,
                      created_at=datetime(2014, 1, 12, 0, 0, 0),
                      content='/sbin/service/nginx status', owner=user)
        Session.add(inl2)

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
