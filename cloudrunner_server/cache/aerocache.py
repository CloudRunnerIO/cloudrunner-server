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
import logging
import os

from cloudrunner import CONFIG_LOCATION
from cloudrunner.util.config import Config
from cloudrunner_server.util import timestamp, MAX_TS

CR_CONFIG = Config(CONFIG_LOCATION)
as_host, as_port = CR_CONFIG.AS_URL or '127.0.0.1', CR_CONFIG.AS_PORT or 3000

config = {
    'hosts': [
        (as_host, int(as_port))
    ],
    'lua': {
        'user_path': os.path.join(
            os.path.dirname(__file__), "functions")
    },
    'policies': {
        'timeout': 1000,  # milliseconds
    }
}

client = aerospike.client(config)
client.connect()
LOG = logging.getLogger('AERO CACHE')
DAYS30 = 30 * 24 * 60 * 60
DAYS7 = 7 * 24 * 60 * 60

LOGS_NS = 'logs'
AUTH_NS = 'auth'
TS_NS = 'timestamps'
USER_NS = 'userdata'
MAX_LOG_LINES = 200
MAX_SCORE = MAX_TS * 1000

# SETS
META_SET = "meta"
OUTPUT_SET = "output"
INDEX_SET = "time-index"
AUTH_TOKEN_SET = "tokens"

LOG.debug("AEROSPIKE CONFIG: %s" % config)


class AeroRegistry(object):

    def __init__(self, **kwargs):
        self.client = client

    def check(self, org, target):
        LOG.info(RegBase.key(TS_NS, org, target))
        try:
            key, meta, last = self.client.get(
                RegBase.key(TS_NS, org, target))
            LOG.info(last)
            if last:
                return last.get('ts', 0)
        except Exception, ex:
            LOG.error(ex)
        return 0

    def put(self, org, key, data, ttl=None):
        policy = {}
        if ttl:
            policy['ttl'] = ttl

        self.client.put(RegBase.key(USER_NS, org, key),
                        data, policy)

    def get(self, org, key):
        k, m, data = self.client.get(RegBase.key(USER_NS, org, key))
        return data

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
        self.org = str(org)
        self.id = str(_id)

        self.client = client

    @classmethod
    def key(cls, *args):
        return tuple([str(a) for a in args])


class RegWriter(RegBase):

    def prepare_log(self, user, ts, ttl=None):
        inc_ops = [
            {
                "op": aerospike.OPERATOR_INCR,
                "bin": "autoid",
                "val": 1
            },
            {
                "op": aerospike.OPERATOR_READ,
                "bin": "autoid"
            }
        ]
        inc_key = self.key(LOGS_NS, META_SET, "inc-%s" % self.org)
        try:
            _, _, data = self.client.operate(inc_key, inc_ops)
        except Exception, (ecode, emsg, efile, eline):
            if ecode == 2:
                self.client.put(inc_key, dict(autoid=0L, org=self.org))
            # retry ...
            _, _, data = self.client.operate(inc_key, inc_ops)
        inc = int(data['autoid'])
        ts = int(ts * 1000)
        key = self.key(LOGS_NS, META_SET, self.id)
        rec = dict(id=inc, uuid=self.id, ts=ts, owner=str(user), org=self.org)

        ttl = {'ttl': ttl or DAYS30}
        self.client.put(key, rec, ttl)

        # Store indexed value
        index_key = dict(key=inc, ts=ts, uuid=self.id)

        self.client.apply((LOGS_NS, INDEX_SET, self.org), 'lstack', 'push',
                          ['autoid', index_key, 'filters'])

    def store_log(self, node, ts, log, user, io='O', ttl=None):
        if not log:
            return

        lines = []
        for l in log.splitlines():
            l = l.strip()
            if l:
                lines.append(str(l))

        ind_key = self.key(LOGS_NS, META_SET, self.id)
        k, m, v = self.client.get(ind_key)
        index = v.get("id", 0)

        ts = int(ts * 1000)
        rec = dict(ts=ts, uuid=self.id, lines=lines, io=io,
                   node=str(node), org=self.org, id=index)
        ttl = {'ttl': ttl or DAYS30}

        key = (LOGS_NS, OUTPUT_SET, "%s-%s" % (self.id, ts))
        self.client.put(key, rec, ttl)

    def store_meta(self, result, ts, ttl=None):
        key = self.key(LOGS_NS, OUTPUT_SET, "%s-meta" % self.id)
        ttl = {'ttl': ttl or DAYS30}
        self.client.put(key, dict(uuid=self.id, org=self.org,
                                  type="meta", result=result))

    def add_token(self, username, token, expire):
        ttl = {'ttl': expire * 60}
        token['username'] = username
        key = self.key(AUTH_NS, AUTH_TOKEN_SET, token['token'])
        self.client.put(key, token, ttl)

    def incr(self, org, what):
        self.client.put(
            self.key(TS_NS, org, what), dict(ts=int(timestamp() * 1000)))


class RegReader(RegBase):

    def __init__(self, client, org):
        self.client = client
        self.org = str(org)
        self.body_filter = None
        self.nodes_filter = None

    def get_user_token(self, user, token):
        key = self.key(AUTH_NS, AUTH_TOKEN_SET, token)
        _, _, val = self.client.get(key)
        if not val:
            return None
        return val

    def log_count(self):
        total = self.client.apply((LOGS_NS, INDEX_SET, self.org),
                                  'lstack', 'size', ['autoid'])
        return total

    def search(self, marker=0, nodes=None, pattern=None, owner=None, limit=50,
               start=None, end=None):
        has_more = True
        if not marker:
            marker = MAX_SCORE
        marker = int(marker)
        i = 1
        if start:
            start = int(start * 1000)
        else:
            start = 0
        if end:
            end = int(end * 1000)
        else:
            end = int(MAX_SCORE)

        filtered = dict()

        while has_more:
            i = i + 1
            # LOG.info("First search between [%s] %s and %s " % (
            #    marker, start, end))
            uuids = self.client.apply((LOGS_NS, INDEX_SET, self.org),
                                      'lstack', 'filter',
                                      ['autoid', limit, 'filters',
                                       'search_ids', dict(marker=marker,
                                                          start_ts=start,
                                                          end_ts=end)])
            if not uuids:
                break
            # LOG.info("First pass: %s" % uuids)
            new_marker = min([u['ts'] for u in uuids])
            if new_marker == marker:
                break
            marker = new_marker
            min_id = int(min([u.get('key', MAX_SCORE) for u in uuids]))
            max_id = int(max([u.get('key', 0) for u in uuids]))

            uuids = set([u['uuid'] for u in uuids])
            if not uuids:
                break

            q = self.client.query(LOGS_NS, OUTPUT_SET)

            LOG.info("Search between %s and %s " % (min_id,
                                                    max_id))
            q.where(p.between('id', min_id, max_id))

            args = dict(org=self.org, nodes=nodes or '',
                        owner=str(owner or ''),
                        uuids=list(uuids),
                        pattern=pattern or '',
                        aggregate=1)

            q.apply('filters', 'search', [args])

            def callback(rec):
                for k in rec:
                    if k in uuids:
                        filtered[k] = rec[k]

            q.foreach(callback)
            # LOG.info("Second pass(filtered): %s" % filtered)

            if filtered:
                break

        if marker == MAX_SCORE:
            marker = 0

        return marker, filtered

    def get_uuid_by_score(self, min_score=0, max_score=MAX_SCORE):
        q = self.client.query(LOGS_NS, OUTPUT_SET)
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

    def load_log(self, min_score=None, max_score=None, uuids=None, tail=None):
        if not uuids:
            return 0, {}

        output = {'new_score': 1}
        min_score = min_score or 0
        max_score = max_score or int(MAX_SCORE)

        def callback(r):
            if r.get('type') == 'meta':
                output['result'] = r.get('result')
                return
            data = output.setdefault(r['uuid'], {})
            output['new_score'] = max(
                output['new_score'], r.get('ts', 0))
            ts = r.get('ts', 0) / 1000.0

            data.setdefault(r['node'],
                            {}).setdefault('lines',
                                           []).append([ts,
                                                       r['lines'],
                                                       r['io']])
        for uuid in uuids:
            q = self.client.query(LOGS_NS, OUTPUT_SET)
            q.where(p.equals('uuid', str(uuid)))
            q.apply('filters', 'search',
                    [dict(org=self.org, full_map=True,
                          min_score=min_score, max_score=max_score,
                          pattern=self.body_filter,
                          nodes=self.nodes_filter)])

            q.foreach(callback)

        for uuid in uuids:
            log = output.get(uuid, {})
            for node in log.values():
                node['lines'] = sorted(node.get("lines", []),
                                       key=lambda l: l[0])
        new_score = output.pop('new_score', 1)
        return new_score, output

    def apply_filters(self, pattern=None, nodes=None, **kwargs):
        self.body_filter = pattern
        self.nodes_filter = nodes
