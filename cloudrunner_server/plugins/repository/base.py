import abc
from functools import wraps  # noqa


class PluginRepoBase(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def type(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def contents(self, path, rev=None):
        return None

    @staticmethod
    def find(repo_type):
        plugin = [p for p in PluginRepoBase.__subclasses__()
                  if p.type == repo_type]
        if not plugin:
            return None
        return plugin[0]


class NotModified(Exception):
    pass


def retry(count=3):

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            cnt_retry = count
            # Call function
            while cnt_retry:
                try:
                    ret = f(*args, **kwargs)
                    return ret
                except NotModified:
                    raise
                except Exception:
                    cnt_retry -= 1
                    if not cnt_retry:
                        return None, None, None
        return wrapper

    return decorator


try:
    from .github import GithubPluginRepo  # noqa
    assert GithubPluginRepo
except ImportError:
    pass

try:
    from .bitbucket import BitbucketPluginRepo  # noqa
    assert BitbucketPluginRepo
except ImportError:
    pass

try:
    from .dropbox_ import DropboxPluginRepo  # noqa
    assert DropboxPluginRepo
except ImportError, ex:
    print ex
    pass
