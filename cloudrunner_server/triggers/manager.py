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
from datetime import datetime
import json
import logging
import os
import re
import redis
from sqlalchemy.orm import (scoped_session, sessionmaker,
                            joinedload, make_transient)
try:
    import argcomplete
except ImportError:
    pass

from cloudrunner import CONFIG_LOCATION, LOG_DIR
from cloudrunner.core import parser
from cloudrunner.core.message import Queued, DictWrapper
from cloudrunner.util import timestamp
from cloudrunner.util.config import Config
from cloudrunner.util.daemon import Daemon
from cloudrunner.util.logconfig import configure_loggers
from cloudrunner.util.shell import colors
from cloudrunner_server.api.model import *  # noqa
from cloudrunner_server.api.server import Master
from cloudrunner_server.plugins.repository.base import (PluginRepoBase,
                                                        NotModified)
from cloudrunner_server.util.db import checkout_listener
from cloudrunner_server.util.cache import CacheRegistry
from cloudrunner_server.api.util import JsonOutput as O

CONFIG = Config(CONFIG_LOCATION)
LOG_LOCATION = os.path.join(LOG_DIR, "cloudrunner-trigger.log")

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
            'exec', help='Execute cron job')
        exec_.add_argument('job_name', help='Job name')
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
            LOG.warn(ex)
            pass

        if hasattr(self.args, 'pidfile'):
            super(TriggerManager, self).__init__(self.args.pidfile,
                                                 stdout='/tmp/log')
        elif self.args.action in ['start', 'stop', 'restart']:
            print colors.red("The --pidfile option is required"
                             " with [start, stop, restart] commands",
                             bold=1)
            exit(1)

    def _prepare_db(self, user_id=None, recreate=False):
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

    def get_user_ctx(self, user_id):
        user = self.db.query(User).join(
            Org).filter(User.id == user_id,
                        User.active == True).one()  # noqa
        return DictWrapper(
            db=self.db,
            _user=user,
            user=DictWrapper(id=user.id,
                             name=user.username,
                             org=user.org.name))

    def _roles(self, ctx):
        user_roles = dict([(role.servers, role.as_user)
                           for role in ctx._user.roles])
        for group in ctx._user.groups:
            user_roles.update(dict([(role.servers, role.as_user)
                                    for role in group.roles]))
        roles = {'org': ctx._user.org.name, 'roles': user_roles}
        return roles

    def choose(self):
        kwargs = vars(self.args)
        action = kwargs.pop('action')
        getattr(self, action)(**kwargs)

    def execute(self, user_id=None, script_name=None, content=None,
                parent_uuid=None, trigger=None, **kwargs):
        LOG.info("Starting %s " % script_name)
        self._prepare_db(user_id=user_id)
        self.db.begin()
        remote_tasks = []
        local_runs = []
        batch_id = None
        ctx = self.get_user_ctx(user_id)
        try:
            tags = kwargs.get('tags', [])
            if tags:
                tags = sorted(re.split(r'[\s,;]', tags))
            timeout = kwargs.get('timeout', 0)

            if not content:
                script = _parse_script_name(ctx, script_name)
                if script:
                    script_content = script.content
                else:
                    LOG.warn("Empty script")
                    return
            else:
                script_content = content.content
                script = Revision(name="Anonymous", content=script_content)
                self.db.add(script)
                self.db.commit()
                self.db.begin()
            env = kwargs.get('env')
            if env and not isinstance(env, dict):
                kwargs['env'] = env = json.loads(env)

            if script.script and script.script.mime_type == 'text/batch':
                batch = script.script.batch
                if not batch:
                    return O.error("Workflow seems to be a Batch, "
                                   "but no Batch found")
                script_step = next((s for s in batch.scripts if s.root), None)
                script = script_step.script
                if not script:
                    return O.error("Batch step points to invalid script")
                script = _parse_script_name(ctx, script.full_path())
                script_content = script.content
                batch_id = batch.id
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
                group.batch_id = batch_id
                self.db.add(group)

            triggered_by = None
            if trigger:
                if isinstance(trigger, int):
                    triggered_by = self.db.query(TriggerType).filter(
                        TriggerType.id == trigger).first()
                    if triggered_by:
                        triggered_by = triggered_by[0]
                    else:
                        triggered_by = None
                else:
                    triggered_by = trigger
            sections = parser.parse_sections(script_content)

            if not sections:
                return O.error(msg="Empty script")

            LOG.info("Execute %s by %s" % (script_name or job,
                                           ctx.user.name))

            task = Task(status=LOG_STATUS.Running,
                        group=group,
                        parent_id=parent_id,
                        owner_id=ctx.user.id,
                        revision_id=script.id,
                        exec_start=timestamp(),
                        timeout=timeout,
                        trigger=triggered_by)
            self.db.add(task)
            for tag in tags:
                task.tags.append(Tag(name=tag))

            for i, section in enumerate(sections):
                parts = [section.body]
                atts = []
                if i == 0:
                    if section.env and section.env._items:
                        # Pre-fill section static env
                        env = section.env._items.update(env)

                if section.args.timeout:
                    timeout = section.args.timeout[0]

                ins = 0
                for arg, scr_names in section.args.items():
                    if arg == 'include-before':
                        for scr in scr_names:
                            s = _parse_script_name(ctx, scr)
                            parts.insert(ins, s.content)
                            ins += 1
                    if arg == 'include-after':
                        for scr in scr_names:
                            s = _parse_script_name(ctx, scr)
                            parts.insert(ins, s.content)

                if section.args.attach:
                    atts = section.args.attach
                remote_task = dict(attachments=atts, body="\n".join(parts))
                if timeout:
                    remote_task['timeout'] = timeout
                remote_task['target'] = self._expand_target(section.target)

                run = Run(task=task,
                          lang=section.args.lang,
                          exec_start=timestamp(),
                          exec_user_id=ctx.user.id,
                          target=section.target,
                          exit_code=-99,
                          timeout=timeout,
                          step_index=i,
                          full_script=section.body,)
                if i == 0:
                    run.env_in = json.dumps(env)

                self.db.add(task)
                remote_tasks.append(remote_task)
                local_runs.append(run)
                self.db.add(run)

            self.db.commit()
            self.db.begin()

            if not remote_tasks:
                self.db.rollback()
                return

            msg = Master(ctx.user.name).command('dispatch',
                                                tasks=remote_tasks,
                                                roles=self._roles(ctx),
                                                includes=[],
                                                attachments=[],
                                                env=env)
            if not isinstance(msg, Queued):
                return

            cache = CacheRegistry(redis=self.redis)
            LOG.info("TASK UUIDs: %s" % msg.task_ids)
            for i, job_id in enumerate(msg.task_ids):
                for tag in tags:
                    cache.associate(ctx.user.org, tag, job_id)
                # Update
                run = local_runs[i]
                run.uuid = job_id
            if msg.task_ids:
                self.db.commit()
            return O.task_ids(_list=msg.task_ids)

        except Exception, ex:
            LOG.exception(ex)
            self.db.rollback()

        return {}

    def resume(self, user_id=None, task_uuid=None):
        try:
            self._prepare_db(user_id=user_id)
            self.db.begin()
            ctx = self.get_user_ctx(user_id)
            task = Task.visible(ctx).filter(Task.uuid == task_uuid).one()
            task.id = None
            task.started_by_id = None
            self.db.expunge(task)
            make_transient(task)
            atts = []
            env = {}
            try:
                if task.env_in:
                    env = json.loads(task.env_in)
            except:
                pass
            remote_task = dict(attachments=atts, body=task.full_script)
            remote_task['target'] = self._expand_target(task.target)
            msg = Master(ctx.user.name).command('dispatch',
                                                tasks=[remote_task],
                                                roles=self._roles(ctx),
                                                includes=[],
                                                attachments=[],
                                                env=env)
            if not isinstance(msg, Queued):
                return
            task.created_at = datetime.now()
            task.uuid = msg.task_ids[0]
            self.db.add(task)
            self.db.commit()
            self.db.begin()

        except Exception, ex:
            LOG.exception(ex)
            self.db.rollback()
        return 1

    def _expand_target(self, target):
        targets = [t.strip() for t in target.split(" ")]
        groups = self.db.query(NodeGroup).filter(
            NodeGroup.name.in_(targets)).all()
        expanded_nodes = set(targets)
        for g in groups:
            for n in g.nodes:
                expanded_nodes.add(n.name)

        return " ".join(expanded_nodes)

    def run(self, **kwargs):
        self._prepare_db()
        LOG.info('Listening for events')

        pubsub = self.redis.pubsub()

        jobs = self.db.query(Job).filter(Job.enabled == True).all()  # noqa
        pubsub.psubscribe('jobs:*')
        patterns = {}

        for job in jobs:
            pattern = None
            pubsub.psubscribe("task:*")
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
                    elif target == 'task':
                        job_data = json.loads(item['data'])
                        kwargs['env'] = job_data.get('env', {})
                        task = self.db.query(Task).join(Run).filter(
                            Run.uuid == job_data['id']).first()
                        if (not task or not task.group.batch or
                                task.status != LOG_STATUS.Finished):
                                # Intermediate step - skip
                            continue
                        src_script_step = [
                            s for s in task.group.batch.scripts
                            if s.script == task.script_content.script]
                        conditions = [c for c in task.group.batch.conditions
                                      if c.source in src_script_step]
                        passed = [c for c in conditions
                                  if c.evaluate(job_data)]
                        seen = []
                        for p in passed:
                            script_name = p.destination.script.full_path()
                            if p.destination.version:
                                script_name = "%s@%s" % (script_name,
                                                         p.destination.version)
                            if p.destination.id in seen:
                                continue
                            seen.append(p.destination.id)
                            trigger = TriggerType(
                                name="Internal",
                                type=p.type,
                                arguments=p.arguments)
                            self.db.begin()
                            self.db.add(trigger)
                            self.db.commit()
                            job_uuid = self.execute(
                                user_id=task.owner.id,
                                script_name=script_name,
                                parent_uuid=task.uuid,
                                trigger=trigger,
                                **kwargs)
                            LOG.info("Executed %s/%s" % (
                                job_uuid, script_name))
                    else:
                        LOG.warn("Unrecognized pattern: %s" % item['pattern'])
            except Exception, ex:
                LOG.error(ex)
            except KeyboardInterrupt:
                break
        LOG.info('Exited main thread')


def _parse_script_name(ctx, path):
    path = path.lstrip("/")
    rev = None
    scr_, _, rev = path.rpartition("@")
    if not scr_:
        scr_ = rev
        rev = None
    if rev and (rev.isdigit() or len(rev) == 8):
        pass
    else:
        scr_ = path
    repo_name, _, full_path = scr_.partition("/")
    repo = Repository.visible(ctx).filter(
        Repository.name == repo_name).one()
    try:
        q = Script.load(ctx, scr_)
        s = q.one()

        if rev:
            return s.contents(ctx, rev=rev)
    except:
        LOG.error("Cannot find %s" % scr_)
        raise
    if repo.type != 'cloudrunner':
        plugin = PluginRepoBase.find(repo.type)
        if not plugin:
            LOG.warn("No plugin found for repo %s" % (repo.type,))
            return None
        plugin = plugin(repo.credentials.auth_user,
                        repo.credentials.auth_pass)
        try:
            contents, last_modified, rev = plugin.contents(
                full_path, rev=rev,
                last_modified=s.contents(ctx).created_at)
            exists = s.contents(ctx, rev=rev)
            if not exists:
                exists = Revision(created_at=last_modified,
                                  version=rev, script=s,
                                  content=contents)
            else:
                exists.content = contents
                exists.created_at = last_modified
            ctx.db.add(exists)

            ctx.db.commit()
            ctx.db.begin()
            return exists
        except NotModified:
            return s.contents(ctx)
    else:
        return s.contents(ctx)

    return None


def main():
    man = TriggerManager()
    man.parse_cli()
    man.choose()

if __name__ == '__main__':
    main()
