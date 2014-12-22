CloudRunner.io Server
=======================


Copyright (c) 2013-2014 CloudRunner.io

SERVICE CONFIGURATION

-------------------------------

* Initial setup

Decide whether to use multi-tenant or single-tenant:

.. code-block:: bash

    cloudrunner-master config set security.use_org=True|False

Then configure server

.. code-block:: bash

    cloudrunner-master config create


* Starting the service

From console

.. code-block:: bash
    cloudrunner-dsp run

or as a daemon:

.. code-block:: bash
    cloudrunner-dsp start --pidfile=file.pid


As a service from packages:

.. code-block:: bash

    service cloudrunner-dsp start


