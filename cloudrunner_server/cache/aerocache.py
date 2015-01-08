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

from __future__ import print_function
import aerospike
import aerospike.predicates as p
from contextlib import contextmanager
import json
import logging
import os
import redis as r

from cloudrunner import CONFIG_LOCATION
from cloudrunner.util.config import Config
from cloudrunner_server.util import timestamp, MAX_TS

CR_CONFIG = Config(CONFIG_LOCATION)
as_host, as_port = CR_CONFIG.AS_URL or '127.0.0.1', CR_CONFIG.AS_PORT or 3000
r_host, r_port = (CR_CONFIG.REDIS_URL or '127.0.0.1',
                  CR_CONFIG.REDIS_PORT or 6379)

redis = r.Redis(host=r_host, port=r_port, db=0)

config = {
    'hosts': [
        (as_host, as_port)
    ],
    'lua': {
        'user_path': os.path.join(os.path.dirname(__file__), "functions")
    },
    'policies': {
        'timeout': 1000,  # milliseconds
        'retry': 2,
    }
}

client = aerospike.client(config)
client.connect()
LOG = logging.getLogger('AERO CACHE')
DAYS30 = 30 * 24 * 60 * 60
DAYS7 = 7 * 24 * 60 * 60

LOGS_SET = 'logs'
TS_SET = 'timestamps'
MAX_LOG_LINES = 200
MAX_SCORE = MAX_TS * 1000


class AeroRegistry(object):

    def __init__(self, **kwargs):
        self.client = client

    def check(self, org, target):
        LOG.info(RegBase.key(TS_SET, org, target))
        try:
            key, meta, last = self.client.get(
                RegBase.key(TS_SET, org, target))
            LOG.info(last)
            if last:
                return last.get('ts', 0)
        except Exception, ex:
            LOG.error(ex)
        return 0

    def associate(self, org, tag, *ids):
        pass
        # client.get((TS_SET, org, target))

    @contextmanager
    def writer(self, org, _id):
        try:
            yield RegWriter(self.client, org, _id)
        except Exception, ex:
            LOG.exception(ex)
            # Do not execute on error
        finally:
            pass

    @contextmanager
    def reader(self, org):
        try:
            yield RegReader(self.client, org)
        except Exception, ex:
            # Do not execute on error
            LOG.exception(ex)
        finally:
            pass


class RegBase(object):

    def __init__(self, client, org, _id):
        self.org = org
        self.id = str(_id)

        self.client = client

    @classmethod
    def key(cls, *args):
        return tuple([str(a) for a in args])


class RegWriter(RegBase):

    def store_log(self, node, ts, log, user, io='O', ttl=None):
        if not log:
            return

        key = self.key(LOGS_SET, self.org, "%s_%s" % (self.id, ts))
        lines = log.splitlines()
        if io != 'O':
            lines = ['\x00\x00' + l for l in lines]

        rec = dict(uuid=self.id, ts=int(ts * 1000), lines=lines, io=io,
                   node=str(node), owner=str(user), type='output')
        ttl = {'ttl': ttl or DAYS30}
        LOG.info("sending %s : %s" % (ts, lines))
        self.client.put(key, rec, ttl)

        redis.publish(self.id, 'update')

    def store_meta(self, result, ts, ttl=None):
        key = self.key(LOGS_SET, self.org, self.id)
        ttl = {'ttl': ttl or DAYS30}
        self.client.put(key, dict(type='meta',
                                  uuid=self.id,
                                  result=result),
                        ttl)

    def notify(self, org, what):
        self.client.put(
            self.key(TS_SET, org, what), dict(ts=int(timestamp() * 1000)))

    def final(self, msgid=None, **kwargs):
        msg = dict(id=msgid, **kwargs)
        redis.publish("task:end", json.dumps(msg))


class RegReader(RegBase):

    def __init__(self, client, org):
        self.client = client
        self.org = org
        self.body_filter = None
        self.nodes_filter = None

    def get_uuid_by_score(self, min_score=0, max_score=MAX_SCORE):
        q = self.client.query(LOGS_SET, self.org)
        q.select('uuid', 'ts')
        q.where(p.between('ts', int(min_score), int(max_score)))

        lines = set()

        def callback((k, m, rec)):
            if rec.get('ts'):
                lines.add((rec['uuid'], rec['ts']))

            # if len(lines) > MAX_LOG_LINES:
            #     return False

        q.foreach(callback)
        lines = sorted(lines, key=lambda l: l[1])
        ret = zip(*lines)

        if ret:
            return ret[1][-1], ret[0]
        else:
            return 0, []

    def load_log(self, min_score=None, max_score=None,
                 nodes=None, uuids=None, tail=None):
        if not nodes and not uuids:
            return 0, {}

        output = {'new_score': 1}
        min_score = min_score or 0
        max_score = max_score or int(MAX_SCORE)
        for uuid in uuids:
            q = self.client.query(LOGS_SET, self.org)
            q.where(p.equals('uuid', uuid))

            q.apply('filters', 'score', min_score, max_score,
                    self.body_filter, self.nodes_filter)

            data = {}

            def callback(rec):
                if "ts" in rec:
                    output['new_score'] = max(output['new_score'], rec['ts'])
                if rec['type'] == 'output':
                    data.setdefault(rec['node'],
                                    {}).setdefault('lines',
                                                   []).append([rec['ts'],
                                                               rec['lines']])
                elif rec['type'] == 'meta':
                    for node in rec.get('nodes', []):
                        data.setdefault(node, {})['result'] = rec['result']

            q.foreach(callback)
            for node in data:
                lines = data[node].get("lines", [])
                if lines:
                    lines = sorted(lines, key=lambda l: l[0])
            output[uuid] = data

        new_score = output.pop('new_score', 1)
        return new_score, output

    def apply_filters(self, pattern=None, nodes=None, **kwargs):
        self.body_filter = pattern
        self.nodes_filter = nodes
