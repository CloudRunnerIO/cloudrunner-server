.. _library:

Library Controller
==================

Provides functions for library

.. note::

	* This controller requires authentication headers. See how to add headers in request: :ref:`secure-headers`

.. _workflows:

Workflows
---------

List workflows
^^^^^^^^^^^^^^

**[GET] /rest/library/workflows/**

	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/workflows

	Response::

		{
			"workflows": {
				"cloudrunner": [
					{
						"created_at": "2014-07-08 00:53:23",
						"name": "scripts/wf1",
						"owner": "cloudr",
						"visibility": "public"
					},
					{
						"created_at": "2014-07-08 00:53:23",
						"name": "scripts/wf2",
						"owner": "cloudr",
						"visibility": "public"
					},
					{
						"created_at": "2014-07-08 00:53:23",
						"name": "scripts/wf3",
						"owner": "cloudr",
						"visibility": "private"
					}
				]
			}
		}

Retrieve workflow details
^^^^^^^^^^^^^^^^^^^^^^^^^

**[GET] /rest/library/workflows/<item_name>**

	**Params**

		<item_name>

			Workflow to retrieve

	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/workflows/wf_item1

	Response::

		{
			"workflow": {
				"content": "#! switch [*]\ncloudrunner-node details",
				"created_at": "2014-07-08 00:53:23",
				"name": "scripts/wf3",
				"owner": "cloudr",
				"visibility": "private"
			}
		}

Create new workflow
^^^^^^^^^^^^^^^^^^^

**[POST] /rest/library/workflows/**

	**POST data**

		<name>

			Creates new workflow

		<content>

			Workflow content

		<?private>

			Optional, defaults to False.

			0 : Public
			1 : Private

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/workflows \
			-d name=wf_item1&content="some content"&private=1

	Response::

		{
			"status": "ok"
		}

Update workflow
^^^^^^^^^^^^^^^

**[PUT] /rest/library/workflows/**

or

**[PATCH] /rest/library/workflows/**

	**POST data**

		<name>

			Workflow name

		<content>

			Workflow content

	Request::

		curl -X PUT -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/workflows/ \
			-d name=wf_item1&content="some modified content"&

	Response::

		{
			"status": "ok"
		}

Delete workflow
^^^^^^^^^^^^^^^

**[DELETE] /rest/library/workflows/<name>**

	**Params**

		<name>

			Workflow name

	Request::

		curl -X DELETE -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/workflows/wf_item1

	Response::

		{
			"status": "ok"
		}

.. _inlines:

Inlines
-------

List inline
^^^^^^^^^^^

**[GET] /rest/library/inlines/**

	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/inlines

	Response::

		{
			"inlines":
			[
				{
					"owner": "testuser",
					"created_at": "2014-06-30 22:31:14",
					"name": "tools/ifconfig"
				},
				{
					"owner": "testuser",
					"created_at": "2014-06-30 22:31:14",
					"name": "tools/nginx_status"
				}
			]
		}

Retrieve inline details
^^^^^^^^^^^^^^^^^^^^^^^

**[GET] /rest/library/inlines/<item_name>**

	**Params**

		<item_name>

			Inline to retrieve

	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/workflows/wf_item1

	Response::

		{
			"inline": {
				"content": "echo \"IN TEST\"\nexport TEST=\"1\"",
				"created_at": "2014-06-30 22:31:14",
				"name": "test",
				"owner": "cloudr"
			}
		}

Create new inline
^^^^^^^^^^^^^^^^^

**[POST] /rest/library/inlines/**

	**POST data**

		<name>

			Creates new inline

		<content>

			Inline content

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/inlines \
			-d name=inl_item1&content="some content"&

	Response::

		{
			"status": "ok"
		}

Update inline
^^^^^^^^^^^^^

**[PUT] /rest/library/inlines/**

or

**[PATCH] /rest/library/inlines/**

	**POST data**

		<name>

			Inline name

		<content>

			Inline content

	Request::

		curl -X PUT -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/inlines/ \
			-d name=inl_item1&content="some modified content"&

	Response::

		{
			"status": "ok"
		}

Delete Inline
^^^^^^^^^^^^^

**[DELETE] /rest/library/inlines/<name>**

	**Params**

		<name>

			Inline name

	Request::

		curl -X DELETE -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/library/inlines/wf_item1

	Response::

		{
			"status": "ok"
		}

Error handling
^^^^^^^^^^^^^^

.. seealso:: :ref:`error-handling`