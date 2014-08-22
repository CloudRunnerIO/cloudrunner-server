import logging
from functools import wraps  # noqa
from pecan import request, abort

LOG = logging.getLogger()


def check_policy(*args):
    permissions = set(args)

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Call function
            if not request.user.permissions.intersection(permissions):
                abort(401)

            return f(*args, **kwargs)
        return wrapper

    return decorator
