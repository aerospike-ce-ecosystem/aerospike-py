import os as _os

AEROSPIKE_CONFIG = {
    "hosts": [
        (
            _os.environ.get("AEROSPIKE_HOST", "127.0.0.1"),
            int(_os.environ.get("AEROSPIKE_PORT", "18710")),
        )
    ],
    # Must match cluster-name in scripts/aerospike.template.conf
    "cluster_name": _os.environ.get("AEROSPIKE_CLUSTER_NAME", "docker"),
}

# Lightweight config for unit tests that never connect to a real server.
# Use a non-standard port (19999) so the connection always fails, even in CI
# where an Aerospike server may be running on port 3000.
DUMMY_CONFIG = {"hosts": [("127.0.0.1", 19999)]}
