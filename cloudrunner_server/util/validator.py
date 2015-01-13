import re

VALID_NODE_NAME = re.compile(r'^[a-zA-Z0-9\-_\.]+$')
VALID_SCRIPT_NAME = re.compile(r"^[\w\-. ]+$")


def valid_node_name(*args):
    if not args:
        return None

    if len(args) == 1:
        return VALID_NODE_NAME.match(args[0])
    else:
        return [n for n in args if VALID_NODE_NAME.match(n)]


def valid_script_name(*args):
    if not args:
        return None

    if len(args) == 1:
        return VALID_SCRIPT_NAME.match(args[0])
    else:
        return [n for n in args if VALID_SCRIPT_NAME.match(n)]
