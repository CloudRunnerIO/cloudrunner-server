import json
import logging

LOG = logging.getLogger()


class DeploymentParser(object):

    def __init__(self, config):
        self.config = config

    def parse(self, content):
        if not isinstance(content, dict):
            content = json.loads(content)
        self.steps = StepCollection(content["steps"])


class StepCollection(list):

    def __init__(self, items):
        super(StepCollection, self).__init__()
        for item in items:
            self.append(Step(item))


class Step(object):

    def __init__(self, data):
        self.target = data.get('target')
        self.content = data.get('content')
        self.path = None
        self.timeout = int(data.get('timeout', 0))
        self.env = json.loads(data.get('env', '{}'))

        if isinstance(self.content, dict):
            if getattr(self.content, 'path'):
                self.path = self.content['path']
            elif getattr(self.content, 'text'):
                self.text = self.content['text']
