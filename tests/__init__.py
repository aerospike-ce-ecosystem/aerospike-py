import os as _os

AEROSPIKE_CONFIG = {
    "hosts": [
        (
            _os.environ.get("AEROSPIKE_HOST", "127.0.0.1"),
            int(_os.environ.get("AEROSPIKE_PORT", "18710")),
        )
    ],
    "cluster_name": "docker",
}
