from functools import wraps
import logging
import redis
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from cloudrunner_server.api.model import *  # noqa
from cloudrunner_server.plugins.logs.base import (LoggerPluginBase,
                                                  FrameBase)
from cloudrunner_server.util.cache import CacheRegistry
from cloudrunner_server.util.db import checkout_listener

LOG = logging.getLogger('DB LOGGER')


def wrap_error(f):
    @wraps(f)
    def wrapper(*args):
        try:
            self = args[0]
            res = f(*args)
            self.db.commit()
            return res
        except Exception, ex:
            LOG.exception(ex)
            self.db.rollback()
    return wrapper


class DbLogger(LoggerPluginBase):

    def __init__(self, config):
        self.db_path = config.db
        self.cache = CacheRegistry(config=config)
        redis_host = config.redis or '127.0.0.1:6379'
        host, port = redis_host.split(':')
        self.r = redis.Redis(host=host, port=port, db=0)

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
                  result=None, step_id=None):
        try:
            log = self.db.query(Log).join(Step, User, Org).filter(
                Log.uuid == session_id,
                Org.name == org).one()
            if step_id + 1 == len(log.steps):
                log.status = LOG_STATUS.Finished
            success = True
            for node in result:
                success = success and (str(node['ret_code']) == '0')
            if success:
                log.exit_code = 0
            else:
                log.exit_code = 1
            self.db.add(log)
            self.db.commit()
        except Exception, ex:
            LOG.exception(ex)
            self.db.rollback()

    @wrap_error
    def log(self, msg):
        frame = FrameBase.create(msg)
        LOG.debug(frame)
        with self.cache.writer(msg.org, msg.session_id) as cache:
            cache.store(frame)
            if frame.frame_type == "S":
                self._finalize(user=msg.user, session_id=msg.session_id,
                               org=msg.org, result=msg.result,
                               step_id=msg.step_id)
                cache.notify("logs")

        if frame.frame_type == "S":
            if msg.env:
                for k in msg.env.keys():
                    self.r.publish('env:%s' % k, msg.session_id)
        elif frame.frame_type == "B":
            if msg.stdout:
                self.r.publish('output:%s' %
                               msg.stdout, msg.session_id)
            if msg.stderr:
                self.r.publish('output:%s' %
                               msg.stderr, msg.session_id)
