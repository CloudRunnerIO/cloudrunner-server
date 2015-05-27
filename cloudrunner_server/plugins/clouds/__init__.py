from .base import BaseCloudProvider  # noqa
from .amazon import AWS  # noqa
from .digitalocean import DigitalOcean  # noqa
from .docker_host import Docker  # noqa
# from .azure import Azure  # noqa

__all__ = [BaseCloudProvider, AWS, DigitalOcean, Docker]
