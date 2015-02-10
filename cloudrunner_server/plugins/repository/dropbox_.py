from datetime import datetime
from dropbox.client import DropboxClient, ErrorResponse
import logging
import json

from .base import PluginRepoBase, NotModified, NotAccessible, retry
TIME_FORMAT = '%a, %d %b %Y %H:%M:%S +0000'
LOG = logging.getLogger('Dropbox plugin')


class DropboxPluginRepo(PluginRepoBase):

    type = 'dropbox'

    def __init__(self, auth_user, auth_pass, *args):
        self.client = DropboxClient(auth_user)

    @retry(default=(None, None, None))
    def browse(self, repo, path, last_modified=None):
        folders = []
        scripts = []
        try:
            res = self.client.metadata(path, hash=last_modified)
            meta = res['contents']
            etag = res['hash']
            if 'modified' in res:
                last_modified = datetime.strptime(res['modified'], TIME_FORMAT)
            else:
                last_modified = None
            for item in meta:
                base_len = len(filter(None, path.strip("/").split("/")))
                item_path = item['path'].strip("/")
                _path = "/".join(item_path.split("/")[base_len:])
                if item['is_dir']:
                    folders.append(dict(name=_path))
                else:
                    scripts.append(dict(name=_path))

            contents = dict(folders=folders, scripts=scripts)
            return contents, last_modified, etag
        except ErrorResponse, err:
            LOG.info("[%s] NOT MODIFIED" % path)
            if err.status == 304:
                raise NotModified()
            else:
                raise NotAccessible()
        except Exception, ex:
            LOG.exception(ex)
            raise NotAccessible()

    @retry(default=(None, None, None, None))
    def contents(self, repo, path, rev=None, last_modified=None):
        if rev:
            revisions = self.client.revisions(path)
            db_rev = [r['rev'] for r in revisions
                      if r['revision'] == int(rev)][0]
        else:
            db_rev = None

        LOG.info("Contents hash: [%s], rev: [%s]" % (last_modified, rev))

        try:
            f = self.client.get_file(path, rev=db_rev)
            meta = json.loads(f.getheader('x-dropbox-metadata'))
            modified = datetime.strptime(meta['modified'], TIME_FORMAT)
            if last_modified:
                if not isinstance(last_modified, datetime):
                    last_modified = datetime.strptime(last_modified,
                                                      TIME_FORMAT)
                if last_modified >= modified:
                    raise NotModified()
            content = f.read()
            return (content, modified, rev or 'HEAD', modified)
        except NotModified:
            raise
        except ErrorResponse, err:
            LOG.info("[%s] : [%s]" % (path, err.status))
            if err.status == 304:
                raise NotModified()
            else:
                LOG.info(err.reason)
                raise NotAccessible()
        except Exception, ex:
            LOG.exception(ex)
            raise NotAccessible()
