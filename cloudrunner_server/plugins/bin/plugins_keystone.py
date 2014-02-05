from os import path as p


def install():
    print "Installing CloudRunner Keystone Plugin"
    from cloudrunner import CONFIG_LOCATION
    from cloudrunner.util.config import Config

    print "Found master config in %s" % CONFIG_LOCATION

    config = Config(CONFIG_LOCATION)
    _path = p.abspath(p.join(p.dirname(__file__), '..', 'transport'))

    config.update('General', 'auth',
                  'cloudrunner_server.plugins.config.auth.KeystoneAuth')

    DEFAULT_URL = "http://127.0.0.1:5000/v2.0"
    print "Enter Keystone AUTH URL (Hit ENTER for default: %s)" % DEFAULT_URL
    auth_url = raw_input('> ')
    if not auth_url:
        auth_url = DEFAULT_URL

    DEFAULT_ADMIN_URL = auth_url.replace(':5000', ':35357')
    print "Enter Keystone AUTH ADMIN URL (Hit ENTER for default: %s)" % \
        DEFAULT_ADMIN_URL
    admin_url = raw_input('> ')
    if not admin_url:
        admin_url = DEFAULT_ADMIN_URL

    print "Enter Keystone admin user:"
    admin_user = raw_input('> ')

    print "Enter Keystone admin password:"
    admin_pass = raw_input('> ')

    config.update('General', 'auth',
                  'cloudrunner_server.plugins.auth.keystone_auth.KeystoneAuth')
    config.update('General', 'auth.auth_url', auth_url)
    config.update('General', 'auth.auth_admin_url', admin_url)
    config.update('General', 'auth.auth_user', admin_user)
    config.update('General', 'auth.auth_pass', admin_pass)
    config.reload()

    if not config.security.use_org:
        print "WARNING: Security::use_org is not set!"

    print "Keystone configuration completed"

if __name__ == '__main__':
    install()
