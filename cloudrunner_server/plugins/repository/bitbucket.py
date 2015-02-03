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
REPO_TIME_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
LOG = logging.getLogger('Bitbucket plugin')


class BitbucketPluginRepo(PluginRepoBase):

    type = 'bitbucket'

    def __init__(self, auth_owner, auth_key, auth_secret):
        consumer = o.Consumer(key=auth_key, secret=auth_secret)
        self.owner = auth_owner
        self.client = o.Client(consumer)

    # @retry(None, None, None)
    def browse(self, repo, path, last_modified=None):
        args = dict(user=self.owner, repo=repo, path=path, rev='HEAD')
        bb_path = REPO_PATH % args
        meta, data = self.client.request(bb_path)

        modified = datetime.strptime(meta['last-modified'], REPO_TIME_FORMAT)

        data = json.loads(data)
        folders, scripts = [], []
        for d in data['directories']:
            folders.append(dict(name=d))
        base_len = len(filter(None, path.strip("/").split("/")))
        for f in data['files']:
            item_path = f['path'].strip("/")
            _path = "/".join(item_path.split("/")[base_len:])
            scripts.append(dict(name=_path,
                                created_at=datetime.strptime(f['utctimestamp'],
                                                             TIME_FORMAT)))

        return dict(folders=folders,
                    scripts=scripts), modified, meta['last-modified']

    # @retry(None, None, None, None)
    def contents(self, repo, full_path, rev=None, last_modified=None):
        args = dict(user=self.owner, repo=repo, path=full_path,
                    rev=rev or 'HEAD')
        bb_path = REPO_PATH % args
        meta, data = self.client.request(bb_path)
        data = json.loads(data)
        if not meta['status'] == '200':
            return None, None, None, None

        commit_path = COMMIT % args
        meta, c_data = self.client.request(commit_path)
        c_data = json.loads(c_data)
        modified = datetime.strptime(c_data['utctimestamp'], TIME_FORMAT)

        etag = c_data['revision']
        if last_modified and modified <= last_modified:
            raise NotModified()

        content = data['data']
        return (content, modified, rev or 'HEAD', etag)
