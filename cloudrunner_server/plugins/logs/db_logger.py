from functools import wraps
import json
import logging
import redis
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from cloudrunner.util import timestamp
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
            task = self.db.query(Task).join(User, Org).join(
                Run, Task.runs).filter(
                    Run.uuid == session_id, Org.name == org).one()
            run = [r for r in task.runs if r.uuid == session_id][0]
            success = True
            run.exec_end = timestamp()
            task.exec_end = timestamp()
            if msg.env:
                run.env_out = json.dumps(msg.env)
            for node, ret in result.items():
                success = success and (str(ret['ret_code']) == '0')
                rnode = RunNode(name=node, exit_code=ret['ret_code'],
                                as_user=ret['remote_user'], run=run)
                self.db.add(rnode)
            if success:
                run.exit_code = 0
            else:
                run.exit_code = 1
            if all([r.exit_code != -99 for r in task.runs]):
                task.status = LOG_STATUS.Finished
                task.exit_code = int(any([bool(r.exit_code)
                                          for r in task.runs]))
            self.db.add(run)
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
                cache.store_log(msg.node, msg.ts, log, io)

        elif msg.control == "FINISHEDMESSAGE":
            self._finalize(msg)
            with self.cache.writer(msg.org, msg.session_id) as cache:
                cache.store_meta(msg.result, msg.ts)

            cache.final(msg.session_id, env=msg.env)
            cache.notify("logs")

        elif msg.control == "INITIALMESSAGE":
            with self.cache.writer(msg.org, msg.session_id) as cache:
                cache.prepare_log()
            cache.notify("logs")
