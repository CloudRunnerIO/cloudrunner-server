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
from mock import MagicMock
import os
from pecan.testing import load_test_app
from pecan import conf as p_conf, set_config

from cloudrunner.util.crypto import hash_token
from ...tests.base import BaseTestCase
from ..model import *  # noqa

aerospike = MagicMock()
aerospike_p = MagicMock()
cache = MagicMock()
ccont = MagicMock()

modules = {
    'aerospike': aerospike,
    'aerospike.predicates': aerospike_p,
    'cloudrunner_server.util.cache': cache,
    'cloudrunner_server.master.functions': ccont
}


class BaseRESTTestCase(BaseTestCase):

    @classmethod
    def setUpClass(self):
        BaseRESTTestCase.modules.update(modules)
        super(BaseRESTTestCase, self).setUpClass()

    permissions = ['is_admin']

    def setUp(self):
        super(BaseRESTTestCase, self).setUp()

        os.environ['CR_CONFIG'] = os.path.join(
            os.path.dirname(__file__), '../../api',
            'cr_test.conf'
        )
        self.app = load_test_app(os.path.join(
            os.path.dirname(__file__), '../../api',
            'config_test.py'
        ))

        self.cache = self.modules['cloudrunner_server.util.cache']
        self.aero = self.cache.CacheRegistry()
        self.aero_reader = self.aero.reader().__enter__()
        self.modules = modules
        # assert correct database
        self.assertIsNone(p_conf.sqlalchemy.engine.url.database)
        self.assertEquals(p_conf.sqlalchemy.engine.url.drivername, "sqlite")

        token = dict(uid=1, org="MyOrg", email="email@domain.com",
                     email_hash="123hash", token="1234567890",
                     permissions=self.permissions,
                     tier=dict(name='tier1', nodes=6,
                               total_repos=5,
                               external_repos=True,
                               users=10, groups=10, roles=5))
        get_token = MagicMock(return_value=token)
        self.aero_reader.get_user_token = get_token
        self.populate()

    def tearDown(self):
        super(BaseRESTTestCase, self).tearDown()
        set_config({}, overwrite=True)

    def populate(self):
        Session.bind = p_conf.sqlalchemy.engine
        metadata.bind = Session.bind

        # metadata.drop_all(Session.bind)
        metadata.create_all(Session.bind)

        # User data

        tier1 = UsageTier(name="Free", title="Free", description="Free Tier",
                          total_repos=5, external_repos=True, nodes=6, users=5,
                          groups=5, roles=4, max_timeout=60,
                          max_concurrent_tasks=2, log_retention_days=7,
                          cron_jobs=4, api_keys=5)

        tier2 = UsageTier(name="Pro", title="Pro", description="Pro Tier",
                          total_repos=10, external_repos=True, nodes=20,
                          users=10, groups=10, roles=10, max_timeout=180,
                          max_concurrent_tasks=5, log_retention_days=30,
                          cron_jobs=10, api_keys=20)
        Session.add(tier2)
        org = Org(name='MyOrg', enabled=True, tier=tier1)
        Session.add(org)

        org2 = Org(name='MyOrg2', enabled=False, tier=tier2)
        Session.add(org2)

        self.assertEquals(ccont.create_ca.call_args_list, [])

        p1 = Permission(name='is_admin')
        Session.add(p1)

        user = User(username='testuser',
                    created_at=datetime(2014, 8, 1),
                    password=hash_token('testpassword'), org=org,
                    first_name="User", last_name="One", department="Dept",
                    position="Sr engineer", email="user1@domain.com")
        Session.add(user)
        Session.commit()

        user.permissions.append(p1)

        user2 = User(username='testuser2',
                     created_at=datetime(2014, 8, 2),
                     password=hash_token('testpassword'), org=org2,
                     first_name="User", last_name="Second", department="HR",
                     position="HR manager", email="user2@domain.com")
        Session.add(user2)

        user1_2 = User(username='testuser3',
                       created_at=datetime(2014, 8, 2),
                       password=hash_token('testpassword3'), org=org,
                       phone="555-666-7777",
                       first_name="User", last_name="Second", department="HR",
                       position="HR manager", email="user3@domain.com")
        Session.add(user1_2)
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

        role1_2_1 = Role(user_id=user1_2.id,
                         servers="stg.*", as_user='developer')
        Session.add(role1_2_1)
        role1_2_2 = Role(user_id=user1_2.id,
                         servers="dev.*", as_user='developer')
        Session.add(role1_2_2)

        Session.commit()

        # Repository data
        repo1 = Repository(name='cloudrunner', type='cloudrunner',
                           enabled=True, owner=user, org=org)
        Session.add(repo1)
        repo11 = Repository(name='empty_repo', owner=user, org=org,
                            enabled=True, type='cloudrunner')
        Session.add(repo11)
        repo2 = Repository(name='private', owner=user2, private=True,
                           enabled=True, org=org2, type='cloudrunner')
        Session.add(repo2)

        ext_repo_link = Repository(name='ext_repo', owner=user, private=True,
                                   enabled=True, org=org, type='github')
        Session.add(ext_repo_link)
        ext_repo = Repository(name='ext_repo', private=True,
                              enabled=True, type='github')
        ext_repo_link.linked = ext_repo
        Session.add(ext_repo)

        creds = RepositoryCreds(auth_user='gituser', auth_pass='gitsecret',
                                repository=ext_repo_link)
        Session.add(creds)

        root1 = Folder(name="/", full_name="/", repository=repo1, owner=user)
        Session.add(root1)
        root11 = Folder(name="/", full_name="/", repository=repo11, owner=user)
        Session.add(root11)
        root2 = Folder(name="/", full_name="/", repository=repo2, owner=user)
        Session.add(root2)
        root_ext = Folder(name="/", full_name="/", repository=ext_repo)
        Session.add(root_ext)
        folder1 = Folder(name="/folder1", full_name="/folder1/",
                         created_at=datetime(2014, 1, 10, 0, 0, 0),
                         repository=repo1, owner=user, parent=root1)
        Session.add(folder1)
        folder11 = Folder(name="/folder11", full_name="/folder1/folder11/",
                          created_at=datetime(2014, 4, 10, 0, 0, 0),
                          repository=repo1, owner=user, parent=folder1)
        Session.add(folder11)
        folder2 = Folder(name="/folder2", full_name="/folder2/",
                         created_at=datetime(2014, 2, 10, 0, 0, 0),
                         repository=repo2, owner=user, parent=root2)
        Session.add(folder2)
        folder21 = Folder(name="/folder11", full_name="/folder1/folder11/",
                          created_at=datetime(2014, 1, 12, 0, 0, 0),

                          repository=repo2, owner=user, parent=folder2)
        Session.add(folder21)

        Session.commit()

        wf1 = Script(name='test1', folder=folder1, owner=user,
                     created_at=datetime(2014, 1, 10, 0, 0, 0))
        Session.add(wf1)

        wf2 = Script(name='test2', folder=folder11, owner=user,
                     created_at=datetime(2014, 1, 20, 0, 0, 0),
                     mime_type="text/workflow",
                     )
        Session.add(wf2)

        wf3 = Script(name='test1', folder=folder2, owner=user2,
                     created_at=datetime(2014, 1, 30, 0, 0, 0),
                     )
        Session.add(wf3)

        wf4 = Script(name='test2', folder=folder21, owner=user2,
                     created_at=datetime(2014, 1, 30, 0, 0, 0),
                     mime_type="text/template",
                     )
        Session.add(wf4)

        r1_1 = Revision(draft=False, content="Version 6",
                        script=wf1,
                        created_at=datetime(2014, 1, 1, 11, 0, 0))
        Session.add(r1_1)
        Session.commit()

        r1_2 = Revision(draft=False, content="Version 7",
                        script=wf1,
                        created_at=datetime(2014, 1, 1, 12, 0, 0))
        Session.add(r1_2)

        r1_2draft = Revision(version='2.abc', draft=True,
                             content="Version 7 draft", script=wf1)
        Session.add(r1_2draft)

        r2_1 = Revision(draft=False, content="Version 1", script=wf2,
                        created_at=datetime(2014, 1, 1, 6, 0, 0))
        Session.add(r2_1)
        Session.commit()

        r2_2 = Revision(draft=False, content="Version 2", script=wf2,
                        created_at=datetime(2014, 1, 1, 7, 0, 0))
        Session.add(r2_2)
        Session.commit()

        r2_3 = Revision(draft=False, content="Version 3", script=wf2,
                        created_at=datetime(2014, 1, 1, 8, 0, 0))
        Session.add(r2_3)

        Session.commit()
        r2_3draft = Revision(version='3.cde', draft=True,
                             content="Version 3 Draft", script=wf2,
                             created_at=datetime(2014, 1, 1, 9, 0, 0))
        Session.add(r2_3draft)
        Session.commit()

        r2_4 = Revision(draft=False, content="Version 4 Final",
                        script=wf2, created_at=datetime(2014, 1, 1, 10, 0, 0))
        Session.add(r2_4)
        Session.commit()

        job1 = Job(name="trigger1", enabled=True, exec_period="* * * * *",
                   owner=user, script=r1_2)
        Session.add(job1)
        job2 = Job(name="trigger2", enabled=True, exec_period="0 * * * *",
                   private=True, script=r2_3, owner=user2)
        Session.add(job2)
        Session.commit()

        node1 = Node(name='node1', approved=True, meta='{"ID": "NODE1"}',
                     org=org,
                     joined_at=datetime.strptime('2014-01-01', '%Y-%m-%d'),
                     approved_at=datetime.strptime('2014-01-01', '%Y-%m-%d'))
        Session.add(node1)

        node2 = Node(name='node2', approved=False, meta='{"ID": "NODE2"}',
                     joined_at=datetime.strptime('2014-04-01', '%Y-%m-%d'),
                     org=org2)
        Session.add(node2)

        node3 = Node(name='node3', approved=True, meta='{"ID": "NODE3"}',
                     org=org,
                     joined_at=datetime.strptime('2014-09-01', '%Y-%m-%d'),
                     approved_at=datetime.strptime('2014-11-01', '%Y-%m-%d'))
        Session.add(node3)

        node4 = Node(name='node4', approved=False, meta='{"ID": "NODE4"}',
                     org=org,
                     joined_at=datetime.strptime('2014-09-01', '%Y-%m-%d'))
        Session.add(node4)

        group = NodeGroup(name='one_two', org=org)
        group.nodes.append(node1)
        group.nodes.append(node2)
        Session.add(group)

        tg = TaskGroup()
        Session.add(tg)
        task = Task(group=tg, uuid='1111111111', timeout=90, owner=user,
                    status=2, exit_code=1, script_content=r1_2,
                    created_at=datetime.strptime('2014-01-01', '%Y-%m-%d'))
        Session.add(task)

        run1 = Run(uuid='222222222', lang='python', env_in='{"key": "value"}',
                   timeout=90, exit_code=2, target="node1 node3", task=task,
                   exec_user=user, step_index=1, exec_start=100000000,
                   exec_end=1000000010, full_script="Version 7")
        Session.add(run1)
        run_node1 = RunNode(name='node1', exit_code=0, as_user='root',
                            run=run1)
        run_node2 = RunNode(name='node3', exit_code=1, as_user='admin',
                            run=run1)
        Session.add(run_node1)
        Session.add(run_node2)
        Session.commit()
