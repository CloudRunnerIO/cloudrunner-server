import logging
import requests
import base64
from datetime import datetime

from .base import PluginRepoBase, NotModified, NotAccessible, retry
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
        self.git_user = self.auth_user

    # @retry(default={})
    def browse(self, repo, path, last_modified=None):
        attr = vars(self)
        attr['repo'] = repo.strip("/")
        attr['path'] = path
        git_path = PATH % (attr)
        git_path = git_path.strip("/")

        headers = {}
        if last_modified:
            headers['If-Modified-Since'] = last_modified.strftime(
                TIME_FORMAT)

        auth = None
        if self.auth_pass:
            auth = (self.auth_user, self.auth_pass)
        r = requests.get(git_path, auth=auth, headers=headers)
        LOG.info("Rate Limit Remaining %s" %
                 r.headers.get("X-RateLimit-Remaining"))
        if r.status_code == 200:
            git_contents = r.json()
            contents = {}
            contents['folders'] = sorted(
                [dict(name=f['name'])
                 for f in git_contents if f['type'] in ['dir', 'submodule']],
                key=lambda k: k['name'])
            contents['scripts'] = sorted(
                [dict(name=f['name'])
                 for f in git_contents
                 if f['type'] in ['file', 'symlink']],
                key=lambda k: k['name'])
            return contents, datetime.strptime(r.headers['Last-Modified'],
                                               TIME_FORMAT)
        elif r.status_code == 304:
            LOG.info("Using cached, since %s" % last_modified)
            raise NotModified()
        elif r.status_code == 403:
            # API limit reached
            LOG.warn("API limit reached")
            raise NotAccessible()
        else:
            LOG.error(git_path)
            raise Exception("Cannot load script contents %s" % path)

    # @retry(default=(None, None, None))
    def contents(self, repo, path, rev=None, last_modified=None):
        attr = vars(self)
        attr['path'] = path.strip("/")
        attr['repo'] = repo.strip("/")

        git_path = PATH % (attr)
        LOG.info("GIT PATH %s" % git_path)
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
        elif r.status_code == 403:
            # API limit reached
            LOG.warn("API limit reached")
            raise NotAccessible()
        else:
            LOG.error(git_path)
            raise Exception("Cannot load script contents %s" % path)
