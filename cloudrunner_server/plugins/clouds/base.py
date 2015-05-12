import abc

PROVISION = """curl -s https://raw.githubusercontent.com/CloudRunnerIO/cloudrunner-library/master/bootstrap.sh | CRN_NODE=%(name)s CRN_SERVER=%(server)s CRN_KEY=%(api_key)s bash"""  # noqa


class BaseCloudProvider(object):
    __metaclass__ = abc.ABCMeta

    FAIL = 0
    OK = 1

    @abc.abstractmethod
    def __init__(self, config, credentials):
        pass

    @abc.abstractmethod
    def create_machine(self, name, *args, **kwargs):
        pass

    @abc.abstractmethod
    def delete_machine(self, name, *args, **kwargs):
        pass
