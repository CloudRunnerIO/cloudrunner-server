from functools import wraps  # noqa
import logging

LOG = logging.getLogger()


def check_policy(f, right, **kwargs):
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Call function
        try:
            response = f(*args, **kwargs)
        except Exception, ex:
            LOG.error(ex)
        finally:
            pass
        return response
    return wrapper
