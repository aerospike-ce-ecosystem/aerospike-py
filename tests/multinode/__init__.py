"""Scenarios that need a node to fail while another keeps answering.

They run against the two-node cluster of ``compose.multinode.yaml`` and stop
one of its nodes, so they carry the ``destructive`` marker and are not part of
any default run::

    make run-aerospike-multinode
    make test-multinode
"""

import os as _os

#: Seed of the two-node cluster (node 1; node 2 is the one the tests stop).
MULTINODE_CONFIG = {
    "hosts": [
        (
            _os.environ.get("AEROSPIKE_MULTINODE_HOST", "127.0.0.1"),
            int(_os.environ.get("AEROSPIKE_MULTINODE_PORT", "18720")),
        )
    ],
    # Must match CLUSTER_NAME in compose.multinode.yaml
    "cluster_name": _os.environ.get("AEROSPIKE_MULTINODE_CLUSTER_NAME", "multinode"),
}

#: Container the scenarios stop and start again.
VICTIM_CONTAINER = _os.environ.get("AEROSPIKE_MULTINODE_VICTIM", "aerospike-node-2")
#: Container that must stay up.
SURVIVOR_CONTAINER = _os.environ.get("AEROSPIKE_MULTINODE_SURVIVOR", "aerospike-node-1")
