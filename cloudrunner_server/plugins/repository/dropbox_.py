import logging
import json
from dropbox.client import DropboxClient
from datetime import datetime

from .base import PluginRepoBase, NotModified, retry
TIME_FORMAT = '%a, %d %b %Y %H:%M:%S +0000'
LOG = logging.getLogger('Dropbox plugin')


class DropboxPluginRepo(PluginRepoBase):

    type = 'dropbox'

    def __init__(self, auth_user, auth_pass):
        self.client = DropboxClient(auth_pass)

    @retry()
    def browse(self, repo, path, last_modified=None):
        return dict(folders=[], scripts=[]), None

    @retry()
    def contents(self, repo, full_path, rev=None, last_modified=None):
        user, _, path = full_path.partition('/')
        if rev:
            revisions = self.client.revisions(path)
            db_rev = [r['rev'] for r in revisions
                      if r['revision'] == int(rev)][0]
        else:
            db_rev = None
        f = self.client.get_file(path, rev=db_rev)
        content = f.read()
        meta = json.loads(f.getheader('x-dropbox-metadata'))
        modified = datetime.strptime(meta['modified'], TIME_FORMAT)
        if last_modified and modified <= last_modified:
            raise NotModified()
        return (content, modified, rev or '__LAST__')
