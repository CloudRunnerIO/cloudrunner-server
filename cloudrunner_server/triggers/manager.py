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

import argparse
import json
import logging
import re
import redis
from sqlalchemy.orm import scoped_session, sessionmaker, joinedload
try:
    import argcomplete
except ImportError:
    pass

from cloudrunner import CONFIG_LOCATION, LOG_LOCATION
from cloudrunner.core import parser
from cloudrunner.core.message import Queued, DictWrapper
from cloudrunner.util.config import Config
from cloudrunner.util.daemon import Daemon
from cloudrunner.util.logconfig import configure_loggers
from cloudrunner.util.shell import colors
from cloudrunner_server.api.model import *  # noqa
from cloudrunner_server.api.server import Master
from cloudrunner_server.util.db import checkout_listener
from cloudrunner_server.util.cache import CacheRegistry

CONFIG = Config(CONFIG_LOCATION)

if CONFIG.verbose_level:
    configure_loggers(getattr(logging, CONFIG.verbose_level, 'INFO'),
                      LOG_LOCATION)
else:
    configure_loggers(logging.DEBUG if CONFIG.verbose else logging.INFO,
                      LOG_LOCATION)

LOG = logging.getLogger("TriggerManager")


class TriggerManager(Daemon):

    """
        Main dispatcher. Receives requests from clients
        and runs them on the specified nodes
    """

    def __init__(self, *_args, **kwargs):
        self.arg_parser = argparse.ArgumentParser()

        controllers = self.arg_parser.add_subparsers(dest='action',
                                                     help='Shell commands')
        service = controllers.add_parser(
            'service',
            help='Start trigger monitoring service')

        service.add_argument('-p', '--pidfile', dest='pidfile',
                             help='Daemonize process with the '
                             'given pid file')
        service.add_argument('-c', '--config', help='Config file')
        service.add_argument(
            'action', choices=['start', 'stop', 'restart', 'run'],
            help='Apply action on the daemonized process\n'
            'For the actions [start, stop, restart] - pass a pid file\n'
            'Run - start process in debug mode\n')

        exec_ = controllers.add_parser(
            'execute', help='Start trigger monitoring service')
        exec_.add_argument('script_name', help='Script name')
        exec_.add_argument('-u', '--user_id', help='User Id', required=True)
        exec_.add_argument('-c', '--config', help='Config file')
        exec_.add_argument('-s', '--source_type', help='Source type')
        exec_.add_argument('-t', '--tags', help='Comma-separated tags')
        exec_.add_argument('-e', '--env', help='Environment')

        if _args:
            self.args = self.arg_parser.parse_args(_args)

        global CONFIG
        if 'config' in kwargs:
            CONFIG = Config(kwargs['config'])

    def parse_cli(self):
        self.args = self.arg_parser.parse_args()

        try:
            argcomplete.autocomplete(self.arg_parser)
        except Exception, ex:
            LOG.error(ex)
            pass

        if hasattr(self.args, 'pidfile'):
            super(TriggerManager, self).__init__(self.args.pidfile,
                                                 stdout='/tmp/log')
        elif self.args.action in ['start', 'stop', 'restart']:
            print colors.red("The --pidfile option is required"
                             " with [start, stop, restart] commands",
                             bold=1)
            exit(1)

    def _prepare_db(self, recreate=False):
        if hasattr(self, 'db'):
            return
        db_path = CONFIG.db
        engine = create_engine(db_path)
        self.db = scoped_session(sessionmaker(bind=engine,
                                              autocommit=True))
        if 'mysql+pymysql://' in db_path:
            event.listen(engine, 'checkout', checkout_listener)
        metadata.bind = self.db.bind
        if recreate:
            # For tests: re-create tables
            metadata.create_all(engine)

        redis_host = CONFIG.redis or '127.0.0.1:6379'
        host, port = redis_host.split(':')
        self.redis = redis.Redis(host=host, port=port, db=0)

    def choose(self):
        kwargs = vars(self.args)
        action = kwargs.pop('action')
        getattr(self, action)(**kwargs)

    def execute(self, user_id=None, script_name=None,
                parent_uuid=None, job=None, **kwargs):
        self._prepare_db()
        self.db.begin()
        try:
            tags = kwargs.get('tags', [])
            timeout = kwargs.get('timeout', 0)

            user = self.db.query(User).join(
                Org).filter(User.id == user_id).one()
            self.user = DictWrapper(id=user.id,
                                    name=user.username,
                                    org=user.org.name)
            script = Script.find(self, script_name).one()

            env = kwargs.get('env')
            if env and not isinstance(env, dict):
                kwargs['env'] = env = json.loads(env)

            parent = None
            parent_id = None
            if parent_uuid:
                parent = self.db.query(Task).filter(
                    Task.uuid == parent_uuid).options(joinedload(
                        Task.group)).first()
            if parent:
                parent_id = parent.id
                group = parent.group
            else:
                group = TaskGroup()
                self.db.add(group)

            script = script.contents(self)
            if script:
                script_content = script.content
            else:
                LOG.warn("Empty script")
                return
            started_by_id = None
            if job:
                if isinstance(job, int):
                    started_by_id = job
                else:
                    started_by_id = job.id

            task = Task(status=LOG_STATUS.Running,
                        group=group,
                        started_by_id=started_by_id,
                        parent_id=parent_id,
                        owner_id=user.id,
                        revision_id=script.id)
            if tags:
                tags = sorted(re.split(r'[\s,;]', tags))
                for tag in tags:
                    task.tags.append(Tag(name=tag))

            sections = parser.parse_sections(script_content)
            for section in sections:
                timeout = section.args.get('timeout', timeout)

                step = Step(timeout=timeout, lang='bash',
                            target=section.target,
                            script=section.script,
                            env_in=json.dumps(kwargs.get('env')),
                            task=task)
                self.db.add(step)

            kwargs['roles'] = {'org': user.org.name, 'roles': {'*': '@'}}
            kwargs['data'] = script_content
            msg = Master(user.username).command('dispatch', **kwargs)
            if not isinstance(msg, Queued):
                return

            cache = CacheRegistry(redis=self.redis)
            for tag in tags:
                cache.associate(user.org.name, tag, msg.job_id)
            # Update
            task.uuid = msg.job_id
            step.job_id = msg.job_id
            self.db.add(task)
            self.db.add(step)
            self.db.commit()
            LOG.info("JOB UUID: %s" % task.uuid)
            return msg.job_id

        except Exception, ex:
            LOG.exception(ex)
            self.db.rollback()

        return ''

    def run(self, **kwargs):
        self._prepare_db()
        LOG.info('Listening for events')

        pubsub = self.redis.pubsub()

        jobs = self.db.query(Job).filter(Job.enabled == True).all()  # noqa
        pubsub.psubscribe('jobs:*')
        patterns = {}

        for job in jobs:
            pattern = None
            if job.source == SOURCE_TYPE.ENV:
                pattern = "env:%s" % job.arguments
            elif job.source == SOURCE_TYPE.LOG_CONTENT:
                pattern = "output:%s" % job.arguments
            if pattern:
                patterns[job.id] = pattern
                pubsub.psubscribe(pattern)
                LOG.info('Subscribed to %s' % pattern)

        while True:
            try:
                for item in pubsub.listen():
                    if not item['pattern']:
                        continue
                    self.db.expire_all()
                    target, action = item['channel'].split(":", 1)
                    if target == 'jobs':
                        if action == 'create':
                            job_id = int(item['data'])
                            job = self.db.query(Job).filter(
                                Job.id == job_id).first()
                            if job:
                                pattern = None
                                if job.source == SOURCE_TYPE.ENV:
                                    pattern = "env:%s" % job.arguments
                                elif job.source == SOURCE_TYPE.LOG_CONTENT:
                                    pattern = "output:%s" % job.arguments
                                if pattern:
                                    patterns[job.id] = pattern
                                    pubsub.psubscribe(pattern)
                                    LOG.info('Subscribed to %s' % pattern)
                        elif action == 'update':
                            job_id = int(item['data'])
                            job = self.db.query(Job).filter(
                                Job.id == job_id).first()
                            if job and job.arguments != patterns.get(job.id):
                                pattern = patterns.pop(job_id, '')
                                if pattern:
                                    pubsub.punsubscribe(pattern)
                                pubsub.psubscribe(job.arguments)
                                LOG.info('Subscribed to %s' % job.arguments)
                        elif action == 'delete':
                            job_id = int(item['data'])
                            pattern = patterns.pop(job_id, '')
                            if pattern:
                                pubsub.punsubscribe(pattern)
                    # Processing triggers
                    elif target in ['output', 'env']:
                        job_ids = [job_id for job_id, pat in patterns.items()
                                   if pat == item['pattern']]
                        if job_ids:
                            uuid = item['data']
                            self._process(job_ids, target, action, uuid)
                    else:
                        LOG.warn("Unrecognized pattern: %s" % item['pattern'])
            except Exception, ex:
                LOG.error(ex)
            except KeyboardInterrupt:
                break
        LOG.info('Exited main thread')

    def _process(self, job_ids, target, action, uuid):
        LOG.info('Processing event[%s:%s] from %s, triggered jobs: %s' % (
            target, action, uuid, job_ids))

        try:
            log = self.db.query(Task).filter(Task.uuid == uuid).one()
            jobs = self.db.query(Job).filter(Job.id.in_(job_ids)).all()
            for job in jobs:
                kwargs = {}
                if log.owner_id == job.owner_id:
                    # Allow env passing
                    kwargs['env'] = {'env': 'yes'}
                job_uuid = self.execute(
                    user_id=log.owner_id, script_name=job.target.full_path(),
                    parent_uuid=uuid, job=job, **kwargs)
                LOG.info("Executed %s" % job_uuid)
        except Exception, ex:
            LOG.exception(ex)


def main():
    man = TriggerManager()
    man.parse_cli()
    man.choose()

if __name__ == '__main__':
    main()
