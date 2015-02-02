import json
import logging
import oauth2 as o
from datetime import datetime

from .base import PluginRepoBase, NotModified, retry
REPO_PATH = ("https://bitbucket.org/api/1.0/repositories/"
             "%(user)s/%(repo)s/src/%(rev)s/%(path)s")
COMMIT = ("https://bitbucket.org/api/1.0/repositories/"
          "%(user)s/%(repo)s/changesets/%(rev)s")

TIME_FORMAT = '%Y-%m-%d %H:%M:%S+00:00'
LOG = logging.getLogger('Bitbucket plugin')


class BitbucketPluginRepo(PluginRepoBase):

    type = 'bitbucket'

    def __init__(self, auth_user, auth_pass):
        consumer = o.Consumer(key=auth_user, secret=auth_pass)
        self.client = o.Client(consumer)

    @retry()
    def browse(self, repo, path, last_modified=None):
        return dict(folders=[], scripts=[]), None

    @retry()
    def contents(self, repo, full_path, rev=None, last_modified=None):
        user, _, repo_path = full_path.partition('/')
        repo, _, path = repo_path.partition('/')
        args = dict(user=user, repo=repo, path=path, rev=rev or 'HEAD')
        bb_path = REPO_PATH % args
        meta, data = self.client.request(bb_path)
        data = json.loads(data)
        if not meta['status'] == '200':
            return None, None, None

        commit_path = COMMIT % args
        meta, c_data = self.client.request(commit_path)
        c_data = json.loads(c_data)
        modified = datetime.strptime(c_data['utctimestamp'], TIME_FORMAT)

        if last_modified and modified <= last_modified:
            raise NotModified()

        content = data['data']
        return (content, modified, rev or '__LAST__')
