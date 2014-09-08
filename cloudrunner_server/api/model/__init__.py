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

from pecan import conf  # noqa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from .base import metadata
from .nodes import *  # noqa
from .users import *  # noqa
from .library import *  # noqa
from .tasks import *  # noqa
from .triggers import *  # noqa

from cloudrunner_server.util.db import checkout_listener

Session = scoped_session(sessionmaker())


def init_model():
    if 'engine' not in vars(conf.sqlalchemy)['__values__']:
        url = conf.cr_config.db
        config = dict(conf.sqlalchemy)
        conf.sqlalchemy.engine = create_engine(url, **config)
        if 'mysql+pymysql://' in url:
            event.listen(conf.sqlalchemy.engine,
                         'checkout',
                         checkout_listener)


def start():
    Session.bind = conf.sqlalchemy.engine
    metadata.bind = Session.bind
    # print "DROPPING & CREATING TABLES"
    # metadata.drop_all(conf.sqlalchemy.engine, tables=[Workflow.__table__, Inline.__table__])  # noqa
    # metadata.drop_all(conf.sqlalchemy.engine)  # noqa
    # metadata.create_all(conf.sqlalchemy.engine)  # noqa
    # populate(Session)


def commit():
    # Session.commit()
    pass


def rollback():
    # Session.rollback()
    pass


def clear():
    # Session.remove()
    pass


def populate(session):
    org = Org(name='DEFAULT', active=True)
    session.add(org)
    session.commit()

    from cloudrunner.util.crypto import hash_token

    demo = User(username='demo', password=hash_token('demo'),
                email='user@site.com', org=org)
    session.add(demo)
    cloudr = User(username='cloudr', password=hash_token('cloudr'),
                  email='cloudr@site.com', org=org)
    session.add(cloudr)
    guest = User(username='guest', password=hash_token('guest'),
                 email='guest@site.com', org=org)
    session.add(guest)

    group1 = Group(name="admin", org=org)
    group1.users.append(demo)
    session.add(group1)

    group2 = Group(name="developers", org=org)
    group2.users.append(cloudr)
    group2.users.append(demo)
    session.add(group2)

    group3 = Group(name="guests", org=org)
    group3.users.append(guest)
    session.add(group3)

    session.commit()

    from datetime import datetime, timedelta
    token = Token(expires_at=datetime.now() + timedelta(minutes=60),
                  scope='LOGIN')
    session.add(token)
    session.commit()
    demo.tokens.append(token)

    r1 = Permission(name='is_admin')
    session.add(r1)
    session.commit()

    demo.permissions.append(r1)
    session.commit()

    role1 = Role(servers='*', as_user='@')
    session.add(role1)
    session.commit()

    role11 = Role(servers='*win*', as_user='Administrator')
    session.add(role11)
    session.commit()

    demo.roles.append(role1)
    session.commit()

    role2 = Role(servers='*', as_user='root')
    session.add(role2)
    group1.roles.append(role2)
    group1.roles.append(role11)
    role3 = Role(servers='*-stg*', as_user='developer')
    session.add(role3)
    group2.roles.append(role3)
    session.commit()

    public = Repository(name="public", owner=demo, org=org)
    private = Repository(name="private", owner=demo, private=True, org=org)

    public_root = Folder(
        name="/", owner=cloudr, repository=public, full_name="/")
    private_root = Folder(
        name="/", owner=cloudr, repository=private, full_name="/")

    folder1 = Folder(name="folder", owner=cloudr, repository=public,
                     parent=public_root, full_name="/folder/")
    folder11 = Folder(name="sub folder", owner=cloudr, repository=public,
                      full_name="/folder/sub folder/", parent=folder1)
    folder2 = Folder(name="my folder", owner=demo, repository=private,
                     parent=private_root, full_name="/my folder/")
    session.add(public)
    session.add(private)
    session.add(folder1)
    session.add(folder11)
    session.add(folder2)
    session.commit()

    scr0 = Script(name='script somewhere', owner=demo, folder=folder11,
                  )
    session.add(scr0)
    session.commit()

    r = Revision(content="#! switch [*]\nhostname", script=scr0)
    session.add(r)
    session.commit()

    scr00 = Script(name='script where', owner=demo, folder=folder1)
    session.add(scr00)
    session.commit()

    r1 = Revision(content="#! switch [*]\nhostname", script=scr00)
    session.add(r1)
    session.commit()

    scr1 = Script(name='scr1', folder=folder1, owner=demo)
    session.add(scr1)
    session.commit()

    r2 = Revision(content="#! switch [*]\nhostname", script=scr1)
    session.add(r2)
    session.commit()

    scr2 = Script(name='scr2', folder=folder1, owner=demo)
    session.add(scr2)
    session.commit()

    r3 = Revision(content="#! switch [*]\ncloudrunner-node details",
                  script=scr2)
    session.add(r3)
    session.commit()

    scr3 = Script(name='scr3', folder=folder1, owner=cloudr)
    session.add(scr3)
    session.commit()

    r4 = Revision(content="#! switch [*]\ncloudrunner-node details",
                  script=scr3)
    session.add(r4)

    scr4 = Script(name='scr4', folder=folder2, owner=demo)
    session.add(scr4)
    session.commit()

    r5 = Revision(content="#! switch [*]\ncloudrunner-node details",
                  script=scr4)
    session.add(r5)

    scr5 = Script(name='scr5', folder=folder2, owner=demo)
    session.add(scr5)
    session.commit()

    r6 = Revision(content="#! switch [*]\ncloudrunner-node details",
                  script=scr5)
    session.add(r6)

    scr6 = Script(name='scr6', folder=folder11, owner=cloudr)
    session.add(scr6)
    session.commit()

    r7 = Revision(content="#! switch [*]\ncloudrunner-node details",
                  script=scr6)
    session.add(r7)

    scr7 = Script(name='scr7', folder=folder11, owner=demo)
    session.add(scr7)
    session.commit()

    r8 = Revision(content="#! switch [*]\ncloudrunner-node details",
                  script=scr7)
    session.add(r8)

    job1 = Job(name="Daily Build", enabled=True, source=SOURCE_TYPE.CRON,
               arguments="0 * * * *", owner=demo, target=scr2)
    session.add(job1)

    job2 = Job(name="Error handler", enabled=True,
               source=SOURCE_TYPE.LOG_CONTENT, arguments="ERROR*",
               owner=demo, target=scr3)
    session.add(job2)

    job3 = Job(name="BitBucket commit", enabled=True,
               source=SOURCE_TYPE.EXTERNAL,
               arguments="ead0bc82d93b4858ba48fafc4c83fba7",
               owner=demo, target=scr3)
    session.add(job3)

    session.commit()
