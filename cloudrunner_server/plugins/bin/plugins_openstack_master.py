from os import path as p


def install():
    print "Installing CloudRunner OpenStack Plugin"
    from cloudrunner import CONFIG_LOCATION
    from cloudrunner.util.config import Config

    print "Found master config in %s" % CONFIG_LOCATION

    config = Config(CONFIG_LOCATION)
    _path = p.abspath(p.join(p.dirname(__file__), '..', 'transport'))

    config.update('Plugins', 'openstack',
                  'cloudrunner_server.plugins.auth.openstack_verifier')
    config.reload()
    if not config.security.use_org:
        print "WARNING: Security::use_org is not set!"

    print "Cloudrunner OpenStack configuration completed"

if __name__ == '__main__':
    install()
