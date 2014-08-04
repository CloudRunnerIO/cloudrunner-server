.. _manage:

Management Controller
==========================

Provides functions for managing users, organizations, roles

.. note::

	* This controller requires authentication headers. See how to add headers in request: :ref:`secure-headers`
	* This controller requires admin role for the calling user. See how to assign application roles: :ref:`secure-headers`

.. _users:

Users
-----


List users
^^^^^^^^^^

**[GET] /rest/manage/users/**


	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/users

	Response::

		{
			"users":
			[
				{
					"name": "cloudr",
					"email": "cloudr@cloudrunner.io",
					"org": "DEFAULT"
				},
				{
					"name": "userX",
					"email": "userX@cloudrunner.io",
					"org": "XOrg"
				}
			]
		}

Create new user
^^^^^^^^^^^^^^^

**[POST] /rest/manage/users/**


	**POST data**::

		<username>
			User name

		<password>
			User's password

		<email>
			User's email

		<org>
			User's organization
			

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/users \
			-d username=userX&password=my_secret&email=em@ail.com&org=DEFAULT

	Response::

		{
			"status": "ok"
		}

Update user details
^^^^^^^^^^^^^^^^^^^

**[PUT] /rest/manage/users/**

or

**[PATCH] /rest/manage/users/**

	**POST data**::

		<username>
			User name

		<?password>
			*Optional*. User's password. If not passed - will not be modified.

		<?email>
			*Optional*. User's email. If not passed - will not be modified.

		<?org>
			*Optional*. User's organization. If not passed - will not be modified.

	Request::

		curl -X PUT -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/users \
			-d username=userX&password=my_new_secret

	Response::

		{
			"status": "ok"
		}

Remove user
^^^^^^^^^^^

**[DELETE] /rest/manage/users/<username>**

	**Params**::

		<username>
			User name

	Request::

		curl -X DELETE -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/users/userX

	Response::

		{
			"status": "ok"
		}

.. _roles:

Roles
-----

Show roles for user
^^^^^^^^^^^^^^^^^^^

**[GET] /rest/manage/roles/<username>**

	**Params**::

		<username>
			User name

	Request::

		curl -X GET -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/roles/userX

	Response::

		{
			"roles":
			[
				{
					"as_user": "root",
					"node": "serverX"
				},
				{
					"as_user": "guest",
					"node": "*"
				},
			]
		}

Add new role for user
^^^^^^^^^^^^^^^^^^^^^

**[POST] /rest/manage/users/<username>**

	**Params**::

		<username>
			User name

	**POST data**::

		<node>
			Node name to allow access for user
			The node could be a regex string. The '*' node is a special wildcard.
			If no specific node matches the request, this default node:role is applied.

		<role>
			Role to assign. The role is usually a local user on the node, i.e. 'root', 'guest'.
			'@' is a special role and means no impersonation, or execute scripts with the user
			that is running the agent.

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/roles/userX \
			-d node=serverY&role=root

	Response::

		{
			"status": "ok"
		}

Delete role for user
^^^^^^^^^^^^^^^^^^^^

**[DELETE] /rest/manage/users/<username>/<node>**

	**Params**::

		<username>
			User name

		<node>
			Node name to revoke access for user

	Request::

		curl -X DELETE -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/roles/userX/serverX \
			-d node=serverY&role=root

	Response::

		{
			"status": "ok"
		}

.. _orgs:

Organizations
-------------

List all organizations
^^^^^^^^^^^^^^^^^^^^^^

**[GET] /rest/manage/orgs**

	Request::

		curl -X GET -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/orgs

	Response::

		{
			"orgs":
			[
				{
					"status": "Active",
					"id": "9a9517ac-a9fa-11e3-8132-00216a5b993e",
					"name": "DEFAULT"
				},
				{
					"status": "Active",
					"id": "fd739b9e-ae8e-11e3-887c-00216a5b993e",
					"name": "MYORG"
				},
				{
					"status": "Active",
					"id": "c2e5942103564a72be12bcd8395bb8b7",
					"name": "neworg"
				}
			]
		}

Add new organization
^^^^^^^^^^^^^^^^^^^^

**[POST] /rest/manage/orgs**

	**POST data**::

		<org>
			User name

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/org \
			-d org=orgX

	Response::

		{
			"status": "ok"
		}

(De)activate an organization
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**[PATCH] /rest/manage/orgs/<org>**

	**Params**::

		<org>
			Organization name

	**POST data**::

		<action>
			0: Deactivate
			1: Activate

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/org/orgX \
			-d action=0

	Response::

		{
			"status": "ok"
		}

Delete organization
^^^^^^^^^^^^^^^^^^^

**[DELETE] /rest/manage/orgs/<org>**

	**Params**::

		<org>
			Organization name

	Request::

		curl -X DELETE -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/manage/orgs/orgX

	Response::

		{
			"status": "ok"
		}

Error handling
^^^^^^^^^^^^^^

.. seealso:: :ref:`error-handling`