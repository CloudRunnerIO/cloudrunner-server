.. _auth:

Authentication Controller
=========================

Performs basic authentication functions:

.. _login:

Login
-----

Initial login, get authentication token
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**[GET] /rest/auth/login/<user>/<password><?expire_after>**

	**Params**

		<user>

			User name

		<password>

			User's password

		<?expire_after>

			*Optional*. Expiration time in minutes

	Request::

		curl https://rest-api-server/auth/login/user/password/2000

	Response::

		{"login":
			{
				"warn": null, 
				"token": "some_very_long_token",
				"expire": "2014-06-25 08:17:53.549138+00:00",
				"user": "user"
			}
		}

Logout, invalidate authentication token
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**[GET] /rest/auth/logout**

	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/auth/logout

	Response::

		{
			"status": "ok"
		}

Error handling
^^^^^^^^^^^^^^

.. seealso:: :ref:`error-handling`