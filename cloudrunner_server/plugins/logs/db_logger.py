from functools import wraps
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from cloudrunner_server.api.model import *  # noqa
from cloudrunner_server.plugins.logs.base import (LoggerPluginBase,
                                                  FrameBase)
from cloudrunner_server.util.cache import CacheRegistry
from cloudrunner_server.util.db import checkout_listener

LOG = logging.getLogger()


def wrap_error(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            self = args[0]
            res = f(*args, **kwargs)
            self.db.commit()
            return res
        except Exception, ex:
            LOG.exception(ex)
            self.db.rollback()
    return wrapper


class DbLogger(LoggerPluginBase):

    def __init__(self, config):
        self.db_path = config.logging.db
        self.cache = CacheRegistry(config=config)

    def set_context_from_config(self, recreate=None, **configuration):
        session = scoped_session(sessionmaker())
        engine = create_engine(self.db_path, **configuration)
        if 'mysql+pymysql://' in self.db_path:
            event.listen(engine, 'checkout', checkout_listener)
        session.bind = engine
        metadata.bind = session.bind
        if recreate:
            # For tests: re-create tables
            metadata.create_all(engine)
        self.db = session

    def _finalize(self, user=None, org=None, session_id=None,
                  result=None, step_id=None, **kwargs):
        log = self.db.query(Log).join(Step, User, Org).filter(
            Log.uuid == session_id,
            Org.name == org).one()
        if step_id + 1 == len(log.steps):
            log.status = LOG_STATUS.Finished
        success = True
        for node in result:
            success = success and (str(node['ret_code']) == '0')
        if not success:
            log.exit_code = 1
            self.db.add(log)

    @wrap_error
    def log(self, **kwargs):
        org = kwargs.pop('org')
        _id = kwargs.pop('session_id')
        frame = FrameBase.create(**kwargs)
        with self.cache.writer(org, _id) as cache:
            cache.store(frame)
            if frame.frame_type == "S":
                self._finalize(session_id=_id, org=org, **kwargs)
