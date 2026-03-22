---
title: Logging
sidebar_label: Logging
sidebar_position: 1
description: Rust-to-Python logging bridge for observing Aerospike client internals.
---

Built-in **Rust-to-Python logging bridge** that forwards all internal Rust logs to Python's `logging` module. Initialized automatically on import.

## Quick Start

```python
import logging
import aerospike_py

logging.basicConfig(level=logging.DEBUG)

client = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]}).connect()
# DEBUG:aerospike_core::cluster: Connecting to seed 127.0.0.1:3000
```

## Log Level Control

```python
aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)
```

| Constant | Value | Python Level |
|---|---|---|
| `LOG_LEVEL_OFF` | -1 | (disabled) |
| `LOG_LEVEL_ERROR` | 0 | ERROR (40) |
| `LOG_LEVEL_WARN` | 1 | WARNING (30) |
| `LOG_LEVEL_INFO` | 2 | INFO (20) |
| `LOG_LEVEL_DEBUG` | 3 | DEBUG (10) |
| `LOG_LEVEL_TRACE` | 4 | TRACE (5) |

## Logger Names

| Logger | Description |
|---|---|
| `aerospike_core::cluster` | Cluster discovery, node management |
| `aerospike_core::batch` | Batch operation execution |
| `aerospike_core::command` | Individual command execution |
| `aerospike_py` | Python-side client wrapper |

```python
# Fine-grained control
logging.getLogger("aerospike_core::cluster").setLevel(logging.DEBUG)
logging.getLogger("aerospike_core::batch").setLevel(logging.WARNING)
```

## JSON Logging

```python
import logging, json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        })

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("aerospike_core")
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)
```

## Framework Integration

### FastAPI

```python
import logging
from contextlib import asynccontextmanager
import aerospike_py
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

@asynccontextmanager
async def lifespan(app: FastAPI):
    aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_INFO)
    client = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
    await client.connect()
    app.state.aerospike = client
    yield
    await client.close()

app = FastAPI(lifespan=lifespan)
```

### Django

```python
# settings.py
LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "aerospike_core": {"handlers": ["console"], "level": "INFO"},
        "aerospike_py": {"handlers": ["console"], "level": "INFO"},
    },
}
```

## File Logging

```python
import logging

handler = logging.FileHandler("aerospike.log")
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

for name in ["aerospike_core", "aerospike_py"]:
    logger = logging.getLogger(name)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
```

## Disabling

```python
aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_OFF)
```
