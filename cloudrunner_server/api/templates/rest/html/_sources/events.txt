.. _events:

Events Controller
==================

Provides support for Server-Sent Events(SSE)

.. seealso::

	* `Server-Sent Events <http://www.w3schools.com/html/html5_serversentevents.asp>`_

.. note::

	* This controller requires authentication headers. See how to add headers in request: :ref:`secure-headers`

Events handler
---------------

Listen to events
^^^^^^^^^^^^^^^^

**[GET] /rest/events/get**

	Request::

		<script>
			var source = new EventSource('https://rest-api-server/rest/events/get');
				source.onmessage = function(e) {
				document.body.innerHTML += e.data + '<br>';
			};
		</script>
