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
from sqlalchemy.orm import (scoped_session, sessionmaker, make_transient)
try:
    import argcomplete
except ImportError:
    pass

from cloudrunner import CONFIG_LOCATION, LOG_DIR
from cloudrunner.util.config import Config
from cloudrunner.util.daemon import Daemon
from cloudrunner.util.logconfig import configure_loggers
from cloudrunner.util.shell import colors
from cloudrunner_server.api.model import *  # noqa
from cloudrunner_server.api.server import Master
from cloudrunner_server.core.message import Queued, DictWrapper
from cloudrunner_server.plugins.repository.base import (PluginRepoBase,
                                                        NotModified)
from cloudrunner_server.util import timestamp
from cloudrunner_server.util.db import checkout_listener
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

        setattr(self, 'exec', self.run_job)
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

    def _prepare_db(self, user_id=None, recreate=False, **kwargs):
        if hasattr(self, 'db'):
            return
        if kwargs.get("db"):
            self.db = kwargs["db"]
        else:
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
                        User.enabled == True).one()  # noqa
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

    def run_job(self, job_name, **kwargs):
        self._prepare_db()
        self.db.begin()

        job = self.db.query(Job).filter(Job.uid == job_name,
                                        Job.enabled == True).first()  # noqa
        if not job:
            LOG.warn("Job not found: %s" % job_name)

        self.db.commit()

        LOG.info("Script '%s' started by job '%s'" % (job.script.script.name,
                                                      job.name))

        self.execute(user_id=job.owner_id, content=job.script,
                     started_by=job.name)

    def execute(self, user_id, deployment, revision=None, **kwargs):
        LOG.info("Starting %s " % deployment.name)
        self._prepare_db(user_id=user_id, **kwargs)
        self.db.begin(subtransactions=True)
        remote_tasks = []
        local_runs = []
        # batch_id = None
        ctx = self.get_user_ctx(user_id)
        try:
            tags = kwargs.get('tags', [])
            if tags:
                tags = sorted(re.split(r'[\s,;]', tags))
            timeout = kwargs.get('timeout', 0)

            env = kwargs.get('env') or {}
            if env and not isinstance(env, dict):
                kwargs['env'] = env = json.loads(env)
            if deployment.env:
                deployment.env.update(env)
                env = deployment.env

            group = TaskGroup(deployment=deployment.object)
            self.db.add(group)

            LOG.info("Execute %s by %s" % (deployment.name, ctx.user.name))
            task = Task(status=LOG_STATUS.Running,
                        group=group,
                        owner_id=ctx.user.id,
                        script_content=revision,
                        exec_start=timestamp(),
                        timeout=timeout,
                        exit_code=-99,
                        script_name=deployment.name)
            self.db.add(task)
            for tag in tags:
                task.tags.append(Tag(name=tag))

            for i, step in enumerate(deployment.steps):
                targets = step.targets
                remote_task = dict(attachments=step.atts, body=step.body,
                                   targets=targets,
                                   timeout=step.timeout, env=step.env or {})
                flat_targets = []
                for t in targets:
                    if isinstance(t, dict):
                        flat_targets.append("%(provider)s::%(name)s" % t)
                    else:
                        flat_targets.append(t)
                run = Run(task=task,
                          lang=step.lang,
                          exec_start=timestamp(),
                          exec_user_id=ctx.user.id,
                          target=" ".join(flat_targets),
                          exit_code=-99,
                          timeout=step.timeout,
                          step_index=i,
                          full_script=step.body)
                if i == 0:
                    run.env_in = json.dumps(env)

                self.db.add(task)
                remote_tasks.append(remote_task)
                local_runs.append(run)
                self.db.add(run)

            self.db.commit()
            self.db.begin(subtransactions=True)

            if not remote_tasks:
                self.db.rollback()
                return

            msg = Master(ctx.user.name).command(
                'dispatch', task_id=group.id,
                tasks=remote_tasks, roles=self._roles(ctx),
                disabled_nodes=self.disabled_nodes(ctx), includes=[],
                attachments=[], env=env)
            if not isinstance(msg, Queued):
                return

            LOG.info("TASK UUIDs: %s" % msg.task_ids)
            for i, job_id in enumerate(msg.task_ids):
                # Update
                run = local_runs[i]
                run.uuid = job_id
            if msg.task_ids:
                self.db.commit()
            return O._anon(task_uid=task.uuid, group=task.taskgroup_id,
                           parent_uid=task.uuid)

        except Exception, ex:
            LOG.exception(ex)
            self.db.rollback()

        return {}

    def resume(self, user_id=None, task_uuid=None, step=None, **kwargs):
        # DEFUNCT
        try:
            self._prepare_db(user_id=user_id, **kwargs)
            self.db.begin(subtransactions=True)
            ctx = self.get_user_ctx(user_id)
            task = Task.visible(ctx).filter(Task.uuid == task_uuid).one()
            task_runs = list(task.runs)
            task.id = None
            task.uuid = None
            task.status = LOG_STATUS.Running
            task.exit_code = -99
            self.db.expunge(task)
            make_transient(task)
            to_remove = []

            for run in sorted(task_runs, key=lambda r: r.step_index):
                if run.step_index < step:
                    to_remove.append(run)
                else:
                    break

            for run in to_remove:
                task_runs.remove(run)

            if not task_runs:
                return O.error(msg="No step found to resume")

            remote_tasks = []
            atts = []
            for i, run in enumerate(task_runs):
                run.step_index = i
                remote_task = dict(attachments=atts, body=run.full_script)
                remote_task['timeout'] = run.timeout
                # remote_task['target'] = self._expand_target(run.target)

                remote_tasks.append(remote_task)

                run.id = None
                run.uuid = None
                run.exit_code = -99
                run.exec_start = timestamp()
                run.exec_user_id = ctx.user.id
                self.db.expunge(run)
                make_transient(run)

            env = kwargs.get("env", {})
            if env and not isinstance(env, dict):
                try:
                    env = json.loads(env)
                except:
                    env = {}
            try:
                env_in = {}
                if task_runs[0].env_in:
                    env_in = json.loads(task_runs[0].env_in) or {}
                if env_in:
                    env_in.update(env)
                    env = env_in
            except Exception, ex:
                LOG.exception(ex)

            msg = Master(ctx.user.name).command(
                'dispatch', tasks=remote_tasks,
                task_id=task.group.id, roles=self._roles(ctx),
                disabled_nodes=self.disabled_nodes(ctx), includes=[],
                attachments=[], env=env)
            if not isinstance(msg, Queued):
                return
            task.created_at = datetime.now()
            task.uuid = msg.task_ids[0]

            for i, job_id in enumerate(msg.task_ids):
                # Update
                run = task_runs[i]
                run.uuid = job_id
                self.db.add(run)
                task.runs.append(run)

            self.db.add(task)
            self.db.commit()
            return O.task_ids(_list=msg.task_ids)

        except Exception, ex:
            LOG.exception(ex)
            self.db.rollback()
        return {}

    def disabled_nodes(self, ctx):
        nodes = [node.name for node in ctx.db.query(Node).filter(
            Node.enabled != True).all()]  # noqa
        return nodes


def include_substitute(ctx, path):
    try:
        scr = _parse_script_name(ctx, path)
    except Exception, ex:
        LOG.exception(ex)
        return "# include '%s' not found" % path
    else:
        if scr:
            return scr.content
    return "# include: %s not found" % path


def _parse_script_name(ctx, path):

    repo_name, name, scr_, rev = Script.parse(path)
    full_path = "/".join([name, scr_])
    parent, _, __ = name.rstrip("/").rpartition("/")
    if parent:
        parent = parent + "/"
    else:
        parent = None

    repo = Repository.visible(ctx).filter(
        Repository.name == repo_name).one()

    if repo.linked:
        parent_repo = repo
        repo = repo.linked
        root_folder = ctx.db.query(Folder).filter(
            Folder.full_name == name, Folder.repository == repo).one()
    else:
        root_folder = Folder.visible(
            request, repo_name, parent=parent).filter(
                Folder.full_name == name).one()

    try:
        s = [sc for sc in root_folder.scripts if sc.name == scr_]
        if not s:
            LOG.error("Cannot find %s" % scr_)
            return None
        else:
            s = s[0]
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
        plugin = plugin(parent_repo.credentials.auth_user,
                        parent_repo.credentials.auth_pass,
                        parent_repo.credentials.auth_args)
        try:
            contents, last_modified, rev = plugin.contents(
                repo_name, full_path, rev=rev,
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
