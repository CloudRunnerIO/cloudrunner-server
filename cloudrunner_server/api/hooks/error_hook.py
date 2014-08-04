import logging
from pecan.hooks import PecanHook

LOG = logging.getLogger()


class ErrorHook(PecanHook):

    priority = 200

    def on_error(self, state, exc):
        LOG.exception(exc)
