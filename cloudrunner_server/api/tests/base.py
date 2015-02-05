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
import os
from pecan.testing import load_test_app
from pecan import conf, set_config
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from cloudrunner.util.crypto import hash_token
from ...tests.base import BaseTestCase
from ..model import *  # noqa

engine = None


class BaseRESTTestCase(BaseTestCase):

    def setUp(self):
        super(BaseRESTTestCase, self).setUp()
        self.app = load_test_app(os.path.join(
            os.path.dirname(__file__), '../../api',
            'config_test.py'
        ))
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
        org = Org(name='MyOrg', enabled=True)
        Session.add(org)

        org2 = Org(name='MyOrg2', enabled=False)
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

        job1 = Job(name="trigger1", enabled=True, source=1,
                   arguments="* * * * *", owner_id=1,
                   target_path='cloudrunner/folder1/folder11/test2')
        Session.add(job1)
        job2 = Job(name="trigger2", enabled=True, source=2, arguments="JOB",
                   target_path='cloudrunner/folder1/test1',
                   owner_id=2)
        Session.add(job2)
        Session.commit()

        node1 = Node(name='node1', approved=True, meta='{"ID": "NODE1"}',
                     org_id=1,
                     joined_at=datetime.strptime('2014-01-01', '%Y-%m-%d'),
                     approved_at=datetime.strptime('2014-01-01', '%Y-%m-%d'))
        Session.add(node1)

        node2 = Node(name='node2', approved=False, meta='{"ID": "NODE2"}',
                     joined_at=datetime.strptime('2014-04-01', '%Y-%m-%d'),
                     org_id=1)
        Session.add(node2)

        node3 = Node(name='node3', approved=True, meta='{"ID": "NODE3"}',
                     org_id=1,
                     joined_at=datetime.strptime('2014-09-01', '%Y-%m-%d'),
                     approved_at=datetime.strptime('2014-11-01', '%Y-%m-%d'))
        Session.add(node3)

        group = NodeGroup(name='one_two', org=org)
        group.nodes.append(node1)
        group.nodes.append(node2)
        Session.add(group)
        task = Task(uuid='1111111111', owner=user, status=2,
                    exit_code=1, target='nodes', full_script='script',
                    env_in='{"key": "value"}', timeout=60, lang='python',
                    script_content=r2_4,
                    created_at=datetime.strptime('2014-01-01', '%Y-%m-%d'))
        Session.add(task)
        Session.commit()
