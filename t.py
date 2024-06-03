from dstack._internal.server.services.runner import client
s = client.ShimClient(port=10998)
s.submit("","", "ubuntu", None)
