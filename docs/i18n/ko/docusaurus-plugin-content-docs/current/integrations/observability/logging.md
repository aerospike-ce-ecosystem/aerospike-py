---
title: Logging
sidebar_label: Logging
sidebar_position: 1
description: Rust-to-Python logging bridge for observing Aerospike client internals.
---

내장 **Rust-to-Python logging bridge** 가 모든 내부 Rust log 를 Python `logging` 모듈로 forward 합니다. import 시 자동 초기화.

## Quick Start

```python
import logging
import aerospike_py

logging.basicConfig(level=logging.DEBUG)

client = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]}).connect()
# DEBUG:aerospike_core::cluster: Connecting to seed 127.0.0.1:3000
```

## Log Level 제어

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

## Logger 이름

| Logger | 설명 |
|---|---|
| `aerospike_core::cluster` | cluster discovery, node 관리 |
| `aerospike_core::batch` | batch operation 실행 |
| `aerospike_core::command` | 개별 command 실행 |
| `aerospike_py` | Python-side client wrapper |

```python
# 세분화된 제어
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

## Framework 통합

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

## Shutdown Fallback

Python GIL 을 사용할 수 없을 때 (예: interpreter shutdown 중) logging bridge 는 메시지를 Python 으로 forward 할 수 없습니다. 이 경우:

- **WARN 과 ERROR** 메시지는 **stderr** 로 emit — 중요한 진단 정보 유실 방지
- **INFO, DEBUG, TRACE** 메시지는 silently drop

drop 된 메시지 수는 `dropped_log_count()` 로 확인:

```python
import aerospike_py

# client shutdown 후
count = aerospike_py.dropped_log_count()
if count > 0:
    print(f"{count} log messages were dropped (GIL unavailable)")
```

## 비활성화

```python
aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_OFF)
```
