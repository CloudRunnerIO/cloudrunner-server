import logging
import requests
import base64
from datetime import datetime

from .base import PluginRepoBase, NotModified, retry
PATH = ('https://api.github.com/repos/%(git_user)s/%(repo)s'
        '/contents/%(path)s')
REV = '?ref=%(rev)s'
TIME_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
LOG = logging.getLogger('Github plugin')


class GithubPluginRepo(PluginRepoBase):

    type = 'github'

    def __init__(self, auth_user, auth_pass):
        self.auth_user = auth_user
        self.auth_pass = auth_pass

    @retry()
    def contents(self, path, rev=None, last_modified=None):
        attr = vars(self)
        path_ = path.lstrip('/')
        git_user, _, user_path = path_.partition('/')
        repo, _, path_ = user_path.partition('/')
        attr['path'] = path_
        attr['repo'] = repo
        attr['git_user'] = git_user

        git_path = PATH % (attr)
        if rev:
            git_path = git_path + REV % dict(rev=rev)

        headers = {}
        if last_modified:
            headers['If-Modified-Since'] = last_modified.strftime(
                TIME_FORMAT)

        r = requests.get(git_path,
                         auth=(self.auth_user, self.auth_pass),
                         headers=headers)
        if r.status_code == 200:
            file_ = r.json()
            content = base64.b64decode(file_['content'])
            return (content, datetime.strptime(r.headers['Last-Modified'],
                                               TIME_FORMAT),
                    rev or '__LAST__')
        elif r.status_code == 304:
            LOG.info("Using cached")
            raise NotModified()
        else:
            LOG.error(r)
            LOG.error(git_path)
            raise Exception("Cannot load script contents %s" % path)
