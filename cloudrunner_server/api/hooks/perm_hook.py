from pecan import abort, request  # noqa
from pecan.hooks import PecanHook


class PermHook(PecanHook):

    priority = 1

    def __init__(self, have=None, dont_have=None):
        super(PermHook, self).__init__()
        self.should_have = set()
        self.should_not_have = set()

        def check_have(perms):
            return self.should_have.intersection(perms)

        def check_dont_have(perms):
            return not self.should_not_have.intersection(perms)

        self.checks = []

        if have:
            self.should_have = have
            self.checks.append(check_have)
        if dont_have:
            self.should_not_have = dont_have
            self.checks.append(check_dont_have)

    def before(self, state):
        p = request.user.permissions

        for check in self.checks:
            if not check(p):
                abort(401)
