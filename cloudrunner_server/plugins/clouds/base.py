import abc
import logging

from cloudrunner.util.config import Config
from cloudrunner import CONFIG_LOCATION

LOG = logging.getLogger()
CONFIG = Config(CONFIG_LOCATION)
PROVISION = """curl -s https://raw.githubusercontent.com/CloudRunnerIO/cloudrunner-library/master/bootstrap.sh | CRN_NODE=%(name)s CRN_SERVER=%(server)s CRN_KEY=%(api_key)s CRN_OVERWRITE=1 bash"""  # noqa
CR_SERVER = CONFIG.master_url or 'master.cloudrunner.io'


class LogWrapper(object):

    def __init__(self, remote_log):
        self.remote = remote_log

    def debug(self, msg, *args):
        LOG.debug(msg, *args)

    def info(self, msg, *args):
        LOG.info(msg, *args)
        if args:
            self.remote(stdout=msg % args)
        else:
            self.remote(stdout=msg)

    def warn(self, msg, *args):
        LOG.warn(msg, *args)
        if args:
            self.remote(stdout=msg % args)
        else:
            self.remote(stdout=msg)

    warning = warn

    def error(self, msg, *args):
        LOG.error(msg, *args)
        if args:
            self.remote(stderr=msg % args)
        else:
            self.remote(stderr=msg)

    def exception(self, msg, *args):
        LOG.exception(msg, *args)
        if args:
            self.remote(stderr=msg % args)
        else:
            self.remote(stderr=msg)


class BaseCloudProvider(object):
    __metaclass__ = abc.ABCMeta

    FAIL = 0
    OK = 1

    def __init__(self, profile, log):
        self.log = LogWrapper(log)
        self.profile = profile
        _api_key = [k for k in self.profile.owner.apikeys if k.enabled]
        if not _api_key:
            raise ValueError("No valid API key for user")
        self.api_key = _api_key[0].value

    @abc.abstractmethod
    def create_machine(self, name, *args, **kwargs):
        pass

    @abc.abstractmethod
    def delete_machine(self, name, *args, **kwargs):
        pass

    @staticmethod
    def find(prof_type):
        plugin = [p for p in BaseCloudProvider.__subclasses__()
                  if p.__name__.lower() == prof_type.lower()]
        if not plugin:
            return None
        return plugin[0]

    @property
    def type(self):
        return self.__class__.__name__
