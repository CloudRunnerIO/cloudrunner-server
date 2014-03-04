__author__ = 'Ivelin Slavov'

from urlparse import urlparse


def parse_dburl(dburl):
    '''
    Parses a db url to dictionary. Available keys are
        res = {
            'dbn': None,
            'driver': None,
            'db': None,
            'user': None,
            'pw': None,
            'host': None,
            'port': None,
        }
    '''
    res = {}
    parsed = urlparse(dburl)
    if "+" in parsed.scheme:
        res['dbn'], res['driver'] = parsed.scheme.split("+", 1)
    else:
        res['dbn'] = parsed.scheme
    if parsed.username:
        res['user'] = parsed.username
    if parsed.password:
        res['pw'] = parsed.password
    if parsed.hostname:
        res['host'] = parsed.hostname
    if parsed.port:
        res['port'] = parsed.port
    db_path = parsed.path
    if parsed.netloc:
        db_path = parsed.path.lstrip('/')
    res['db'] = db_path
    return res
