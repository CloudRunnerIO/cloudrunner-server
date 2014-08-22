from pecan import conf  # noqa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from .base import metadata
from .log import *  # noqa
from .users import *  # noqa
from .library import *  # noqa
from .triggers import *  # noqa

from cloudrunner_server.util.db import checkout_listener

Session = scoped_session(sessionmaker())


def _engine_from_config(configuration):
    configuration = dict(configuration)
    url = configuration.pop('url')
    return create_engine(url, **configuration)


def init_model():
    if 'engine' not in vars(conf.sqlalchemy)['__values__']:
        conf.sqlalchemy.engine = _engine_from_config(conf.sqlalchemy)
        if 'mysql+pymysql://' in conf.sqlalchemy:
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
    token = Token(expires_at=datetime.now() + timedelta(minutes=60))
    session.add(token)
    session.commit()
    demo.tokens.append(token)

    r1 = Right(name='admin')
    session.add(r1)
    session.commit()

    demo.rights.append(r1)
    session.commit()

    role1 = Role(name='default', servers='*', as_user='@')
    session.add(role1)
    session.commit()

    role11 = Role(name='win', servers='*win*', as_user='Administrator')
    session.add(role11)
    session.commit()

    demo.roles.append(role1)
    session.commit()

    role2 = Role(name='root', servers='*', as_user='root')
    session.add(role2)
    group1.roles.append(role2)
    group1.roles.append(role11)
    role3 = Role(name='dev', servers='*-stg*', as_user='developer')
    session.add(role3)
    group2.roles.append(role3)
    session.commit()

    public = Library(name="public", owner=demo, org=org)
    private = Library(name="private", owner=demo, private=True, org=org)

    public_root = Folder(name="/", owner=cloudr, library=public, full_name="/")
    private_root = Folder(
        name="/", owner=cloudr, library=private, full_name="/")

    folder1 = Folder(name="folder", owner=cloudr, library=public,
                     parent=public_root, full_name="/folder/")
    folder11 = Folder(name="sub folder", owner=cloudr, library=public,
                      full_name="/folder/sub folder/", parent=folder1)
    folder2 = Folder(name="my folder", owner=demo, library=private,
                     parent=private_root, full_name="/my folder/")
    session.add(public)
    session.add(private)
    session.add(folder1)
    session.add(folder11)
    session.add(folder2)
    session.commit()

    scr0 = Script(name='script somewhere', owner=demo, folder=folder11,
                  content="#! switch [*]\nhostname")
    session.add(scr0)

    scr00 = Script(name='script where', owner=demo, folder=folder1,
                   content="#! switch [*]\nhostname")
    session.add(scr00)

    scr1 = Script(name='scr1', folder=folder1, owner=demo,
                  content="#! switch [*]\nhostname")
    session.add(scr1)

    scr2 = Script(name='scr2', folder=folder1, owner=demo,
                  content="#! switch [*]\ncloudrunner-node details")
    session.add(scr2)

    scr3 = Script(name='scr3', folder=folder1, owner=cloudr,
                  content="#! switch [*]\ncloudrunner-node details")
    session.add(scr3)

    scr4 = Script(name='scr4', folder=folder2, owner=demo,
                  content="#! switch [*]\ncloudrunner-node details")
    session.add(scr4)

    scr5 = Script(name='scr5', folder=folder2, owner=demo,
                  content="#! switch [*]\ncloudrunner-node details")
    session.add(scr5)

    scr6 = Script(name='scr6', folder=folder11, owner=cloudr,
                  content="#! switch [*]\ncloudrunner-node details")
    session.add(scr6)

    scr7 = Script(name='scr7', folder=folder11, owner=demo,
                  content="#! switch [*]\ncloudrunner-node details")
    session.add(scr7)

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
