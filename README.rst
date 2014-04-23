CloudRunner.io Server
=======================


Copyright (c) 2013-2014 CloudRunner.io

USER environment configuration
-------------------------------

* change your user and pass and username

.. code-block:: bash

    cat > ~/.cloudrunner <<EOF
    export CLOUDRUNNER_USER={username}
    export CLOUDRUNNER_TOKEN={pwd}
    export CLOUDRUNNER_SERVER=tcp://{IP/HOSTNAME}:5559
    EOF

    * Source it before using cloudrunner client:
    source ~/.cloudrunner

    * If we want to have it all the time do:
    echo >> $HOME/.bashrc <<EOF
    source ~/.cloudrunner
    EOF

* Save a script from within the script

.. code-block:: bash

    ---cut---
    #! switch [*] --store-lib=my_script

    echo 123
    ---cut---


* Use a stored script within the script

.. code-block:: bash
    ---cut---
    #! switch [*] --include-lib=my_script

    . my_script
    ---cut---

* List / delete from CLI

.. code-block:: bash

    cloudrunner plugin --arg='--list-libs'
    cloudrunner plugin --arg='--show-lib={some_name}'

* Save a script from CLI

TODO

* Use a stored script from CLI

.. code-block:: bash

    cloudrunner plugins
    cloudrunner run script_name --env='{"user": "username", "pwd": "examplepassword"}'
    # --env passes the some variables to script within

* Add a script to scheduler

.. code-block:: bash
    cloudrunner schedule add --name udpate_build_cloudrunner --period '3 2 * * *' build_update_cloudrunner.crn

# use inline

.. code-block:: bash

    cloudrunner schedule add --name  udpate_build_cloudrunner --period '3 2 * * *' -i "
    #! switch [host=master.novalocal] --include-lib=build_rpms
    . build_rpms

    #! switch [host=master.novalocal] --include-lib=deploy_update_master
    . deploy_update_master

    #! switch [host=*.novalocal] --include-lib=deploy_update_nodes
    . deploy_update_nodes
    "

* Add a saved script from library to scheduler

TODO

