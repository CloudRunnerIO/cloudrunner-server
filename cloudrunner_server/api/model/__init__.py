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

    store = Store(name='cloudrunner', store_type='local')
    session.add(store)
    session.commit()

    scr1 = Script(name='test/scr1', store=store, owner=demo,
                  content="#! switch [*]\nhostname")
    session.add(scr1)

    scr2 = Script(name='test/scr2', store=store, owner=demo,
                  content="#! switch [*]\ncloudrunner-node details")
    session.add(scr2)

    scr3 = Script(name='test/scr3', store=store, owner=demo, private=True,
                  content="#! switch [*]\ncloudrunner-node details")
    session.add(scr3)

    scr4 = Script(name='test/scr4', store=store, owner=cloudr, private=True,
                  content="#! switch [*]\ncloudrunner-node details")
    session.add(scr4)

    scr5 = Script(name='test/scr5', store=store, owner=cloudr,
                  content="#! switch [*]\ncloudrunner-node details")
    session.add(scr5)

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
