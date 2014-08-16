.. _library:

Library Controller
==================

Provides functions for library

.. note::

	* This controller requires authentication headers. See how to add headers in request: :ref:`secure-headers`

.. _scripts:

scripts
---------

List scripts
^^^^^^^^^^^^^^

**[GET] /rest/library/scripts/**

	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/scripts

	Response::

		{
			"scripts": {
				"cloudrunner": [
					{
						"created_at": "2014-07-08 00:53:23",
						"name": "scripts/scr1",
						"owner": "cloudr",
						"visibility": "public"
					},
					{
						"created_at": "2014-07-08 00:53:23",
						"name": "scripts/scr2",
						"owner": "cloudr",
						"visibility": "public"
					},
					{
						"created_at": "2014-07-08 00:53:23",
						"name": "scripts/scr3",
						"owner": "cloudr",
						"visibility": "private"
					}
				]
			}
		}

Retrieve script details
^^^^^^^^^^^^^^^^^^^^^^^^^

**[GET] /rest/library/scripts/<item_name>**

	**Params**

		<item_name>

			script to retrieve

	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/scripts/scr_item1

	Response::

		{
			"script": {
				"content": "#! switch [*]\ncloudrunner-node details",
				"created_at": "2014-07-08 00:53:23",
				"name": "scripts/scr3",
				"owner": "cloudr",
				"visibility": "private"
			}
		}

Create new script
^^^^^^^^^^^^^^^^^^^

**[POST] /rest/library/scripts/**

	**POST data**

		<name>

			Creates new script

		<content>

			script content

		<?private>

			Optional, defaults to False.

			0 : Public
			1 : Private

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/scripts \
			-d name=scr_item1&content="some content"&private=1

	Response::

		{
			"status": "ok"
		}

Update script
^^^^^^^^^^^^^^^

**[PUT] /rest/library/scripts/**

or

**[PATCH] /rest/library/scripts/**

	**POST data**

		<name>

			script name

		<content>

			script content

	Request::

		curl -X PUT -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/scripts/ \
			-d name=scr_item1&content="some modified content"&

	Response::

		{
			"status": "ok"
		}

Delete script
^^^^^^^^^^^^^^^

**[DELETE] /rest/library/scripts/<name>**

	**Params**

		<name>

			script name

	Request::

		curl -X DELETE -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/scripts/scr_item1

	Response::

		{
			"status": "ok"
		}

Error handling
^^^^^^^^^^^^^^

.. seealso:: :ref:`error-handling`