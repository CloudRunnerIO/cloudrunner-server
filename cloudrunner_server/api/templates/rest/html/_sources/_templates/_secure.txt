.. _secure-headers:

Security headers
----------------

This controller needs authentication headers.

**HTTP headers**

	::

		Cr-User:	username
		Cr-Token:	auth_token

**Examples**

	Curl::

		curl -H "Cr-User=user" -H "Cr-Token=token" https://rest-api-server/path/

	Ajax::

		$.ajax({
			type: 'POST',
			url: url,
			beforeSend: function(xhr) { 
				xhr.setRequestHeader("Cr-User", "user"); 
				xhr.setRequestHeader("Cr-Token", "token"); 
			}
		});

.. seealso::

	* :ref:`login`
