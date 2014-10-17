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
from collections import Iterable, OrderedDict
from functools import partial
import logging
from contextlib import contextmanager
import redis as r
import re
import time

LOG = logging.getLogger('REDIS CACHE')
REL_MAP_KEY = "MAPKEYS"


class CacheRegistry(object):

    def __init__(self, config=None, redis=None):
        if config:
            if config.redis:
                self.r_host, self.r_port = config.redis.split(":", 1)
                self.r_port = int(self.r_port)
            else:
                self.r_host, self.r_port = '127.0.0.1', 6379
            self.redis = r.Redis(host=self.r_host, port=self.r_port, db=0)
        elif redis:
            self.redis = redis
        else:
            # default
            self.r_host, self.r_port = '127.0.0.1', 6379
            self.redis = r.Redis(host=self.r_host, port=self.r_port, db=0)

    def check(self, org, target):
        self.switch_db(org, self.redis)
        last_id = self.redis.get(RegBase._get_rel_id(target))
        return last_id

    def check_group(self, org, *tags):
        self.switch_db(org, self.redis)
        pipe = self.redis.pipeline()
        for tag in tags:
            pipe.lrange(RegBase._get_rel_id(tag), -20, -1)
        arrays = pipe.execute()
        for tag_arr in arrays:
            for arr in tag_arr:
                if not arr:
                    continue
                pipe.get(RegBase._get_rel_id(arr))
        ids = [i for i in pipe.execute() if i]
        if ids:
            return max(ids, key=int)
        return 0

    def associate(self, org, tag, *ids):
        self.switch_db(org, self.redis)
        self.redis.rpush(RegBase._get_rel_id(tag), *ids)

    @contextmanager
    def writer(self, org, *args):
        self.switch_db(org, self.redis)
        try:
            yield RegWriter(self.redis, *args)
        except Exception, ex:
            LOG.exception(ex)
            # Do not execute on error
        finally:
            pass

    @contextmanager
    def reader(self, org, *args):
        self.switch_db(org, self.redis)
        try:
            yield RegReader(self.redis, *args)
        except Exception, ex:
            # Do not execute on error
            LOG.exception(ex)
        finally:
            pass

    @staticmethod
    def switch_db(space, redis):
        redis.execute_command("SELECT", "0")
        db_key = "__DB__%s__" % space
        db = redis.get(db_key)
        if not db:
            db = redis.incr("ORGS")
            redis.set(db_key, db)
        # redis.select(db)
        redis.execute_command("SELECT", db)


class RegBase(object):

    def __init__(self, redis, _id):
        self.redis = redis
        map_key = self._get_rel_id("_K", _id)
        map_id = self.redis.get(map_key)
        if not map_id:
            map_id = self.redis.incr(REL_MAP_KEY)
            self.redis.set(map_key, map_id)
        self.id = _id
        self.key = map_id

    @staticmethod
    def _get_rel_id(*args, **kwargs):
        return ":".join([str(a) for a in args] +
                        ["=".join([str(k), str(v)]) for k, v in kwargs.items()
                         if v is not None])


class RegWriter(RegBase):

    def prepare_log(self):
        pass

    def store_log(self, node, ts, log, io='O'):
        if not log:
            return

        s_rel_key = self._get_rel_id('S', self.key, node)
        z_rel_key = self._get_rel_id('Z', self.key, node)
        nodes_key = self._get_rel_id(self.key, 'nodes')
        node_2_uuid_key = self._get_rel_id("N2U", node)
        uuid_key = self._get_rel_id("UU")
        # Update nodes zlist
        self.redis.sadd(nodes_key, node)
        # Update uuid map
        self.redis.zadd(node_2_uuid_key, self.id, ts)
        # Update uuid ts map
        self.redis.zadd(uuid_key, self.id, ts)
        # Store lines into list
        lines = log.splitlines()
        if io != 'O':
            lines = ['\x00\x00' + l for l in lines]
        end = self.redis.rpush(s_rel_key, *lines)
        begin = end - len(lines)

        # Store seq into zlist
        line_range = "%s:%s" % (begin, end)
        self.redis.zadd(z_rel_key,
                        line_range,
                        ts)

        self.redis.publish(self.id, 'update')
        self.redis.set(self.id, ts)

    def store_meta(self, result):
        for node in result:
            rel_key = self._get_rel_id('M', self.key, node)
            self.redis.hmset(rel_key, result[node])

    def notify(self, what):
        self.redis.set(what, time.mktime(time.gmtime()))
        # self.redis.incr(what)


class RegReader(RegBase):

    def __init__(self, redis):
        self.redis = redis.pipeline()
        self.filters = {}
        self.body_filter = None

    def key(self, job_id):
        if not hasattr(self, '_key'):
            map_key = self._get_rel_id("_K", job_id)
            self.redis.get(map_key)
            self._key = self.redis.execute()[0]
        return self._key

    def get_uuid_by_score(self, min_score=0, max_score='inf'):
        uuid_key = self._get_rel_id("UU")
        self.redis.zrangebyscore(uuid_key, min_score, max_score,
                                 withscores=True)
        ret = zip(*self.redis.execute()[0])
        if ret:
            return ret[1][-1], ret[0]
        else:
            return 0, []

    def get_nodes(self, job_id, nodes=None):
        nodes_key = self._get_rel_id(self.key(job_id), 'nodes')
        self.redis.smembers(nodes_key)
        all_nodes = self.redis.execute()[0]
        if nodes:
            all_nodes = all_nodes.intersection(set(nodes))
        return all_nodes

    def get_meta(self, job_id, nodes):
        for node in nodes:
            meta_key = self._get_rel_id("M", self.key(job_id), node)
            self.redis.hgetall(meta_key)
        meta = self.redis.execute()
        return dict(zip(nodes, meta))

    def get_node_log(self, job_id, nodes, begin=0, end=-1):
        for node in nodes:
            s_rel_key = self._get_rel_id('S', self.key(job_id), node)
            self.redis.lrange(s_rel_key, begin, end)
        return zip(nodes, self.redis.execute())

    def get_node_log_by_score(self, job_id, nodes, min_score=0,
                              max_score='inf', tail=None):
        for node in nodes:
            z_rel_key = self._get_rel_id('Z', self.key(job_id), node)
            self.redis.zrevrangebyscore(z_rel_key, max_score, min_score,
                                        withscores=True)
        logs = zip(nodes, self.redis.execute())
        found_nodes = OrderedDict()
        max_score = 0
        node_tail = {}
        for log in logs:
            if log[1]:
                for item in log[1]:
                    node = log[0]
                    range_, score = item
                    node_tail.setdefault(node, 0)
                    max_score = max(score, max_score)
                    begin, end = range_.split(":", 1)
                    begin = int(begin)
                    end = int(end)
                    length = end - begin
                    if tail and node_tail[node] + length > tail:
                        allowed = tail - node_tail[node]
                        begin = end - allowed
                    ts_dict = found_nodes.setdefault(node, OrderedDict())
                    range_ = ts_dict.setdefault(score, [])
                    range_.extend([(begin, end)])
                    node_tail[node] += length
                    if tail and node_tail[node] >= tail:
                        break
        ret = {}
        for node, ts_range in found_nodes.items():
            sectors = OrderedDict()
            s_rel_key = self._get_rel_id('S', self.key(job_id), node)
            for ts, range_ in ts_range.items():
                for r_ in range_:
                    self.redis.lrange(s_rel_key, r_[0], r_[1] - 1)

                sectors[ts] = len(range_)
        l = self.redis.execute()
        for node, ts_range in found_nodes.items():
            for ts, range_ in ts_range.items():
                for r_ in range_:
                    ret.setdefault(node, []).insert(0, (ts, l.pop(0)))

        return ret, max_score

    def load_log(self, min_score, max_score,
                 nodes=None, uuids=None, tail=None):
        if not nodes and not uuids:
            return 0, {}

        new_score = 1
        output = {}
        for u in uuids:
            log = output.setdefault(u, {})

            nodes = self.get_nodes(u, nodes=nodes)
            meta = self.get_meta(u, nodes)
            node_lines, new_score = self.get_node_log_by_score(
                u, nodes, min_score, max_score, tail=tail)
            for node, lines in node_lines.items():
                log_info = log[node] = {}
                log_info['result'] = meta.get(node)
                log_info['lines'] = list(self.content_filter(lines))

        return new_score, output

    def is_match(self, meta):
        if meta and self.filters:
            for k, fn in self.filters.items():
                if not fn(meta.get(k)):
                    return False

        return True

    def content_filter(self, data):
        if not data:
            return
        for item in data:
            if self.body_filter:
                filtered = [line for line in item[1]
                            if self.body_filter.search(line)]
                if filtered:
                    yield (item[0], filtered)

            else:
                yield item

    def apply_filters(self, pattern=None, **kwargs):
        def list_check(v, x):
            return x in v

        def str_check(v, x):
            return x.encode('utf8') == v.encode('utf8')

        for k, v in kwargs.items():

            if v:
                if isinstance(v, Iterable):
                    self.filters[k] = partial(list_check, v)
                else:
                    self.filters[k] = partial(str_check, v)
        if pattern:
            self.body_filter = re.compile(pattern)

    def dump(self, *job_ids):

        for job_id in job_ids:

            print("=" * 10)
            print("Job ID: %s" % job_id)
            print("=" * 10)

            print("=" * 10)
            print("Nodes")
            print("=" * 10)

            nodes = list(self.get_nodes(job_id))
            map(print, nodes)

            print("=" * 10)
            print("Meta")
            print("=" * 10)

            meta = self.get_meta(job_id, nodes)
            print(meta)

            print("=" * 10)
            print("Full log")
            print("=" * 10)

            map(lambda log: print(log[0], repr("\n".join(log[1]))),
                self.get_node_log(job_id, nodes))

            print("=" * 10)
            print("Partial log(2-5 lines)")
            print("=" * 10)

            map(lambda log: print(log[0], "\n".join(log[1])),
                self.get_node_log(job_id, nodes, begin=2, end=5))

            print("=" * 10)
            print("Scored full log")
            print("=" * 10)

            map(lambda log: print(log[0], "\n".join(log[1])),
                self.get_node_log_by_score(job_id, nodes)[0])

            print("=" * 10)
            print("Scored partial log (score = 2:4)")
            print("=" * 10)

            map(lambda log: print(log[0], "\n".join(log[1])),
                self.get_node_log_by_score(job_id, nodes,
                                           min_score=2, max_score=4)[0])
