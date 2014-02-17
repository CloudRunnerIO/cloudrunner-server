..
      Copyright 2014 CloudRunner.IO
      All Rights Reserved.

================
Installation
================


RedHat/Fedora/CentOS
=========================


Set the CloudRunner repo::

      wget -O /etc/yum.repos.d/cr.repo http://www.cloudrunner.io/cr.repo


Then install the repo packages::


      yum install cloudrunner-server

You can install a plugin of your choice. There is a pre-installed plugins
that will work as default, but if you want to add additional features,
add the CloudRunner.Plugins repo::


      rpm -uhv https://www.cloudrunner.io/crn_plugins_repo


and then install a plugin of  your choice::

      yum install cloudrunner_server-plugins-keystone

Usually a plugin may have a confuguration tool after being installed,
look for executable with name like::


      cloudrunner-plugins-[plugin-name]
