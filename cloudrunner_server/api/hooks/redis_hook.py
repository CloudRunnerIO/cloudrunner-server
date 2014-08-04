from pecan import conf, request  # noqa
from pecan.hooks import PecanHook
import redis


class RedisHook(PecanHook):

    priority = 99

    def before(self, state):
        r_server, r_port = conf.redis['host'], conf.redis['port']
        request.redis = redis.Redis(host=r_server, port=int(r_port), db=0)
