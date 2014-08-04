from pecan import conf
import redis

r_server, r_port = conf.redis['host'], conf.redis['port']
redis_client = redis.Redis(host=r_server, port=int(r_port), db=0)
