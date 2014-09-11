from functools import wraps
import logging
import redis
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from cloudrunner.core.message import EnvBroadcast
from cloudrunner_server.api.model import *  # noqa
from cloudrunner_server.plugins.logs.base import LoggerPluginBase
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

    def _finalize(self, msg):
        session_id = msg.session_id
        org = msg.org
        result = msg.result
        try:
            task = self.db.query(Task).join(User, Org).filter(
                Task.uuid == session_id,
                Org.name == org).one()
            task.status = LOG_STATUS.Finished

            success = True
            for node, ret in result.items():
                success = success and (str(ret['ret_code']) == '0')
            if success:
                task.exit_code = 0
            else:
                task.exit_code = 1
            self.db.add(task)
            self.db.commit()
        except Exception, ex:
            LOG.exception(ex)
            self.db.rollback()

    @wrap_error
    def log(self, msg):
        LOG.debug(msg)

        if msg.control == "PIPEMESSAGE":
            if msg.stdout:
                log = msg.stdout
                io = 'O'
            elif msg.stderr:
                log = msg.stderr
                io = 'E'
            else:
                # Empty
                return
            with self.cache.writer(msg.org, msg.session_id) as cache:
                cache.store_log(msg.node, msg.seq_no, msg.ts, log, io)
            if msg.stdout:
                self.r.publish('output:%s' %
                               msg.stdout, msg.session_id)
            if msg.stderr:
                self.r.publish('output:%s' %
                               msg.stderr, msg.session_id)

        elif msg.control == "FINISHEDMESSAGE":
            self._finalize(msg)
            with self.cache.writer(msg.org, msg.session_id) as cache:
                cache.store_meta(msg.result)

            if msg.env:
                for k, v in msg.env.items():
                    pub_msg = EnvBroadcast(msg.session_id, k, v)
                    self.r.publish('env:%s' % k, pub_msg._)
            cache.notify("logs")

        elif msg.control == "INITIALMESSAGE":
            with self.cache.writer(msg.org, msg.session_id) as cache:
                cache.prepare_log()
            cache.notify("logs")
