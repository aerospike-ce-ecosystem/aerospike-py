"""Shared type aliases for aerospike_py."""

from typing import Any

Operation = dict[str, Any]
"""Operation dict with 'op', 'bin', 'val' keys, for use with client.operate()."""
