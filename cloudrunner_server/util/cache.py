from collections import Iterable
from functools import partial
import logging
from contextlib import contextmanager
import redis as r
import re

from cloudrunner_server.plugins.logs.base import FrameBase, BodyFrame

LOG = logging.getLogger()
REL_MAP_KEY = "MAPKEYS"


class CacheRegistry(object):

    def __init__(self, config=None, redis=None):
        if config:
            self.r_host, self.r_port = '127.0.0.1', 6379
            if config.has_section("Logging"):
                self.r_host = config.logging.server_url or self.r_host
                self.r_port = int(config.logging.port or self.r_port)
            self.redis = r.Redis(host=self.r_host, port=self.r_port, db=0)
        elif redis:
            self.redis = redis
        else:
            raise Exception("Provide either config or redis connection")

    def check(self, org, target):
        last_id = self.redis.get(RegBase._get_rel_id(org, target))
        return last_id

    @contextmanager
    def writer(self, org, *args):
        try:
            yield RegWriter(self.redis, org, *args)
        except Exception, ex:
            LOG.exception(ex)
            # Do not execute on error
        finally:
            pass

    @contextmanager
    def reader(self, org, *args):
        try:
            yield RegReader(self.redis, org, *args)
        except Exception, ex:
            # Do not execute on error
            LOG.exception(ex)
        finally:
            pass


class RegBase(object):

    def __init__(self, redis, space, _id):
        self.redis = redis
        map_key = self._get_rel_id(space, "K", _id)
        map_id = self.redis.get(map_key)
        if not map_id:
            map_id = self.redis.incr(REL_MAP_KEY)
            self.redis.set(map_key, map_id)
        self.id = self._get_rel_id(space, _id)
        self.key = map_id

    @staticmethod
    def _get_rel_id(*args, **kwargs):
        return ":".join([str(a) for a in args] +
                        ["=".join([str(k), str(v)]) for k, v in kwargs.items()
                        if v is not None])

    @staticmethod
    def _parse_rel_id(rel_key):
        return rel_key.split(":")


class RegWriter(RegBase):

    def store(self, frame):
        data_key = self._get_rel_id(self.key, **frame.header)
        if frame.body:
            end = self.redis.rpush(data_key, *frame.body)
            begin = end - len(frame.body)
            rel_key = self._get_rel_id(data_key, begin, end)
            self.redis.zadd(self.key,
                            rel_key,
                            int(frame.seq_no))

        self.redis.publish(self.id, 'update')
        self.redis.set(self.id, frame.seq_no)


class RegReader(RegBase):

    def __init__(self, redis, space, *_ids):
        self.redis = redis.pipeline()
        self.ids = []
        self.keys = []
        for _id in _ids:
            self.redis.get(self._get_rel_id(space, "K", _id))
            self.ids.append(_id)

        for out in self.redis.execute():
            map_id = out
            self.keys.append(map_id)

        self.filters = {}
        self.body_filter = None

    def load(self, min_score, max_score):

        new_score = 1
        output = {}
        for fid, key in enumerate(self.keys):
            frames = []
            self.redis.zrangebyscore(key, min_score, max_score,
                                     withscores=True)
            rel_keys = self.redis.execute()[0]

            if not rel_keys:
                self.redis.zcard(key)
                new_score = self.redis.execute()[0]
                return new_score, []

            for rel in rel_keys:
                if not rel:
                    continue

                key, score = rel
                rel_key, beg, end = key.rsplit(":", 2)
                beg, end = int(beg), int(end)

                meta = rel_key.split(":")
                meta.pop(0)  # id

                keys = {}
                for _key in meta:
                    k, v = _key.split('=', 1)
                    keys[k] = v

                frame_data = filter(lambda x: x[0] == rel_key, frames)
                if not frame_data:
                    frame = FrameBase.restore(int(score), **keys)

                    if isinstance(frame,
                                  BodyFrame) and not self.is_match(keys):
                        continue

                    frames.append((rel_key, frame))

                    frame.begin = beg
                    frame.end = end
                else:
                    frame = frame_data[0][1]
                    frame.end = end
                frame.seq_no = score
                new_score = max(new_score, score)

            for rel_key, frame in frames:
                self.redis.lrange(rel_key, frame.begin, frame.end)

            data = self.redis.execute()
            for i, tup in enumerate(frames):
                _, frame = tup
                _data = data[i]
                if isinstance(frame, BodyFrame):
                    if self.is_match(keys):
                        frame.body = self.content_filter(_data)
                    else:
                        frame.body = []
                else:
                    frame.body = _data
            output[self.ids[fid]] = [f[1] for f in frames]
        return new_score, output

    def is_match(self, meta):
        if meta and self.filters:
            for k, fn in self.filters.items():
                if not fn(meta.get(k)):
                    return False

        return True

    def content_filter(self, data):
        if data and self.body_filter:
            for line in data:
                return [line for line in data if
                        self.body_filter.search(line)]

        return data

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
