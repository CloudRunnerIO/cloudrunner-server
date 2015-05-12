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
from sqlalchemy.sql.expression import null

from .base import metadata
from .batches import *  # noqa
from .deployments import *  # noqa
from .nodes import *  # noqa
from .users import *  # noqa
from .library import *  # noqa
from .cloud_profiles import *  # noqa
from .tasks import *  # noqa
from .jobs import *  # noqa

from cloudrunner_server.util.db import checkout_listener

Session = scoped_session(sessionmaker())
NULL = null()


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


def commit():
    # Session.commit()
    pass


def rollback():
    # Session.rollback()
    pass


def clear():
    # Session.remove()
    pass
