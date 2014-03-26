#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed without the express
#  * permission of CloudRunner.io
#  *******************************************************/

import logging

import time
from os import environ

from cloudrunner.shell.runner import CONFIG
from cloudrunner.shell.runner import ShellRunner

LOG = logging.getLogger(__name__)


class CROrchestrator(object):

    def __init__(self, server=None,
                 user=None, password=None, timeout=600):
        self.user = user or environ.get("CLOUDRUNNER_USER",
                                        CONFIG.run_as.user)
        self.password = password or environ.get("CLOUDRUNNER_TOKEN",
                                                CONFIG.run_as.password)
        self.server = server or CONFIG.master or 'tcp://127.0.0.1:5559'
        self.timeout = timeout or 600  # Default 10 min

    def _check_nodes(self, *nodes):
        runner = ShellRunner('list_nodes', '--server=%s' % self.server,
                             '-u=%s' % self.user, '-p=%s' % self.password)
        try:
            success, avl_nodes = runner.list_nodes_get()
            if not success:
                LOG.error("Error getting nodes from Master %s" % avl_nodes)
            approved_nodes = [c.lower() for c in avl_nodes]

            return all([n.lower() in approved_nodes for n in nodes])
        except Exception, ex:
            LOG.exception(ex)
        finally:
            runner.close()
        return []

    def orchestrate(self, recipe, nodes):
        while not self._check_nodes(*nodes):
            time.sleep(5)

        runner = ShellRunner('run', '--server=%s' % self.server,
                             '-i', '-u=%s' % self.user,
                             '-p=%s' % self.password,
                             '-t=%s' % self.timeout,
                             '-#=heat_orchestration',
                             recipe)
        try:
            LOG.info("Starting orchestration")
            job_id = runner.run(detach=True)
            LOG.info("Finished orchestration for job %s" % job_id)
            return job_id
        except Exception, ex:
            LOG.exception(ex)
        finally:
            runner.close()

        return None
