"""Write a bin with a language-specific blob particle type, as old clients did.

Clients released years ago serialised values that have no Aerospike type with
their own language's serialiser and marked the result with a particle type of
its own: a Java client wrote ``JAVA_BLOB``, the official Python client pickled
and wrote ``PYTHON_BLOB``. Clusters that have been alive long enough still hold
such records.

No current client writes them — the official Python client refuses the values
it used to pickle — so the only way to put one on a test server is to say it in
the wire protocol. This module sends that one message: a single-bin write whose
particle type the caller chooses.
"""

from __future__ import annotations

import socket
import struct

# Particle types of the serialised blobs, as the server and every client number them.
JAVA_BLOB = 7
CSHARP_BLOB = 8
PYTHON_BLOB = 9
RUBY_BLOB = 10
PHP_BLOB = 11
ERLANG_BLOB = 12

LANGUAGE_BLOBS = {
    "JAVA_BLOB": JAVA_BLOB,
    "CSHARP_BLOB": CSHARP_BLOB,
    "PYTHON_BLOB": PYTHON_BLOB,
    "RUBY_BLOB": RUBY_BLOB,
    "PHP_BLOB": PHP_BLOB,
    "ERLANG_BLOB": ERLANG_BLOB,
}

_PROTO_VERSION = 2
_PROTO_TYPE_MESSAGE = 3
_MESSAGE_HEADER_SIZE = 22
_INFO2_WRITE = 0x01
_FIELD_NAMESPACE = 0
_FIELD_SET = 1
_FIELD_DIGEST = 4
_OP_WRITE = 2


def _field(field_type: int, data: bytes) -> bytes:
    return struct.pack(">IB", len(data) + 1, field_type) + data


def _receive(connection: socket.socket, size: int) -> bytes:
    chunks = []
    while size:
        chunk = connection.recv(size)
        if not chunk:
            raise ConnectionError("the server closed the connection before answering")
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


def write_bin_with_particle_type(
    address: tuple[str, int],
    namespace: str,
    set_name: str,
    digest: bytes,
    bin_name: str,
    particle_type: int,
    payload: bytes,
    timeout: float = 5.0,
) -> int:
    """Write one bin of ``particle_type`` holding ``payload``; return the server's result code.

    ``digest`` is the record's 20-byte digest, as ``client.exists(key).key.digest``
    reports it. The server must not require authentication.
    """
    name = bin_name.encode()
    operation = (
        struct.pack(">IBBBB", 4 + len(name) + len(payload), _OP_WRITE, particle_type, 0, len(name)) + name + payload
    )
    fields = (
        _field(_FIELD_NAMESPACE, namespace.encode())
        + _field(_FIELD_SET, set_name.encode())
        + _field(_FIELD_DIGEST, digest)
    )
    header = struct.pack(
        ">BBBBBBIIIHH",
        _MESSAGE_HEADER_SIZE,
        0,  # info1: nothing is read
        _INFO2_WRITE,
        0,  # info3
        0,  # unused
        0,  # result code (a request has none)
        0,  # generation
        0,  # record ttl: the namespace default
        int(timeout * 1000),  # transaction ttl, in milliseconds
        3,  # fields: namespace, set, digest
        1,  # operations
    )
    body = header + fields + operation
    proto = struct.pack(">Q", (_PROTO_VERSION << 56) | (_PROTO_TYPE_MESSAGE << 48) | len(body))

    with socket.create_connection(address, timeout=timeout) as connection:
        connection.sendall(proto + body)
        (answer_proto,) = struct.unpack(">Q", _receive(connection, 8))
        answer = _receive(connection, answer_proto & 0xFFFF_FFFF_FFFF)
    return answer[5]
