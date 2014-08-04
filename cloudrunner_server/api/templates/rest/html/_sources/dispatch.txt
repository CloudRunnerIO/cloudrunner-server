.. _dispatch:

Dispatcher Controller
=====================

Provides support for dipatching commands to servers(nodes)

.. note::

	* This controller requires authentication headers. See how to add headers in request::
		:ref:`secure-headers`

Dispatch request
----------------

Send request
^^^^^^^^^^^^

**[POST] /rest/dispatch/send**

	Request::

		{
			"request": {
				"target": "server1 server2 server-dev*",
				"command": "echo $(hostname)"
			}
		}

	Response::

		{
			"result": {
				"id": "12345678-1234-1234-12345678012"
			}
		}
