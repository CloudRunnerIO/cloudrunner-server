.. _triggers:

Triggers Controller
===================

Provides functions for binding events to signals

.. note::

	* This controller requires authentication headers. See how to add headers in request: :ref:`secure-headers`

.. _signals:

Signal bindings
----------------

List current signals
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**[GET] /rest/triggers/bindings**

	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/triggers/create/ \
			-d signal=SIG&target=http://url/to/target&auth=1

	Response::

		{
			"triggers":
			[
				{
					"auth": "True",
					"is_link": "True",
					"signal": "TEST",
					"target": "http://site.com",
					"user": "cloudr"
				},
				{
					"auth": "True",
					"is_link": "True",
					"signal": "BEST",
					"target": "http://site.com",
					"user": "cloudr"
				}
			]
		}

Bind a signal to target workflow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**[POST] /rest/triggers/bindings**

	**POST data**

		<signal>

			The signal name to bind

		<target>

			Target script/workflow to execute on signal event

		<?auth>

			*Optional*. Whether to send authentication headers when retrieving the target script

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/triggers/create/ \
			-d signal=SIG&target=http://url/to/target&auth=1

	Response::

		{
			"status": "ok"
		}

Detach target from signal
^^^^^^^^^^^^^^^^^^^^^^^^^

**[PUT] /rest/triggers/bindings/<signal_name>**

	**Params**

		<signal_name>

			The signal name to bind

	**POST data**

		<target>

			Target script/workflow to execute on signal event

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/triggers/detach/SIG \
			-d target="http://url/to/target""

	Response::

		{
			"status": "ok"
		}

Error handling
^^^^^^^^^^^^^^

.. seealso:: :ref:`error-handling`