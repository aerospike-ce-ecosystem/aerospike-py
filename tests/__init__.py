import os as _os

AEROSPIKE_CONFIG = {
    "hosts": [
        (
            _os.environ.get("AEROSPIKE_HOST", "127.0.0.1"),
            int(_os.environ.get("AEROSPIKE_PORT", "18710")),
        )
    ],
    "cluster_name": _os.environ.get("AEROSPIKE_CLUSTER_NAME", "docker"),
}

# Lightweight config for unit tests that never connect to a real server.
DUMMY_CONFIG = {"hosts": [("127.0.0.1", 3000)]}
