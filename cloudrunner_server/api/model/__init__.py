from pecan import conf  # noqa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from .base import metadata
from .log import *  # noqa
from .users import *  # noqa
from .library import *  # noqa

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
    # metadata.drop_all(conf.sqlalchemy.engine, tables=[Step.__table__, Log.__table__])  # noqa
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

    demo.roles.append(role1)
    session.commit()

    store = Store(name='cloudrunner', store_type='local')
    session.add(store)
    session.commit()

    wf1 = Workflow(name='test/wf1', store=store, owner=demo,
                   content="#! switch [*]\nhostname")
    session.add(wf1)

    wf2 = Workflow(name='test/wf2', store=store, owner=demo,
                   content="#! switch [*]\ncloudrunner-node details")
    session.add(wf2)

    wf3 = Workflow(name='test/wf3', store=store, owner=demo, private=True,
                   content="#! switch [*]\ncloudrunner-node details")
    session.add(wf3)

    wf4 = Workflow(name='test/wf4', store=store, owner=cloudr, private=True,
                   content="#! switch [*]\ncloudrunner-node details")
    session.add(wf4)

    wf5 = Workflow(name='test/wf5', store=store, owner=cloudr,
                   content="#! switch [*]\ncloudrunner-node details")
    session.add(wf5)

    inl1 = Inline(name='tools/ifconfig', content='/sbin/ifconfig', owner=demo)
    session.add(inl1)

    inl2 = Inline(name='tools/nginx_status', private=True,
                  content='/sbin/service/nginx status', owner=demo)
    session.add(inl2)

    inl3 = Inline(name='tools/nginx_statusx', private=True,
                  content='/sbin/service/nginx status', owner=cloudr)
    session.add(inl3)

    inl4 = Inline(name='tools/nginx_statusz', private=False,
                  content='/sbin/service/nginx status', owner=cloudr)
    session.add(inl4)

    session.commit()
