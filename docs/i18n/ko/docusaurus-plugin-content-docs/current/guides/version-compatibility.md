---
title: 버전별 호환성 변경
slug: /guides/version-compatibility
toc_max_heading_level: 2
description: 버전을 올릴 때 기존 호출 코드, 반환값, 저장 데이터에 영향을 주는 변경을 확인하세요.
---

버전을 올릴 때 기존 호출 코드, 반환값, 저장 데이터에 영향을 주는 변경을 확인하세요.

[0.14.x → 0.15](#v0-15) · [0.13.0 → 0.14.0](#v0-14)

## 0.14.x → 0.15 {#v0-15}

0.15 후보판은 Aerospike Rust 클라이언트 3.0을 사용합니다. 아래 표에서 사용하는 기능을 선택하면 0.14.x와 0.15의 동작과 필요한 코드 변경을 비교할 수 있습니다.

예제는 단일 노드 Aerospike CE 8.2에서 두 버전으로 실행했습니다. `client`는 연결된 동기 클라이언트입니다.

### 코드 점검표 {#checklist}

| 코드가 다음에 해당하면 | 읽을 곳 |
|---|---|
| 6.4보다 오래된 Aerospike server를 사용 | [최소 server 버전](#minimum-server-version) |
| `operate_ordered()` 결과를 위치나 bin 이름으로 읽거나, 두 번 응답한 bin을 list로 기대 | [`operate_ordered()`](#operate_ordered-returns-one-entry-per-operation) |
| `BatchRecord`를 이름 네 개로 unpack하거나, `BatchRecord.result` code를 해석 | [Batch 결과](#batch-results) |
| 실패한 batch 호출을 catch한 뒤 아무것도 쓰이지 않았다고 가정 | [전체가 실패한 batch 호출](#a-batch-call-that-fails-as-a-whole-keeps-its-rows) |
| `batch_operate`, `batch_remove`, `batch_apply`, `batch_write`, `batch_write_numpy`가 스스로 다시 보내 주기를 기대 | [Write batch의 자동 retry 중단](#write-batches-no-longer-retry-automatically) |
| `batch_write`에 `retry=N`과 `policy["max_retries"]`를 함께 전달 | [`retry` 인자](#the-retry-argument-of-batch_write) |
| 실패한 UDF를 `ClientError`로, 없는 namespace를 `ClusterError` / `AerospikeTimeoutError`로 catch | [Exception](#exceptions) |
| `POLICY_*` 상수가 아닌 policy 값을 전달 | [Policy 값 검사](#policy-values-are-checked) |
| `aerospike_py.exp`로 만들지 않은 `filter_expression`(문자열, dict 등)을 전달 | [Expression이 아닌 filter](#a-filter_expression-that-is-not-an-expression-is-refused) |
| 예전 client가 언어별 blob(`PYTHON_BLOB`, `JAVA_BLOB`, ...)으로 쓴 record를 읽거나, 그런 record를 건너뛰려고 `RustPanicError`를 catch | [언어별 blob](#records-with-a-language-specific-blob-are-readable) |
| `batch_write_numpy()`나 `to_numpy()`를 사용 | [NumPy batch 읽기와 쓰기](#numpy-batch-reads-and-writes) |
| `batch_write_numpy()`의 key field를 `("_key", "i8", (1,))` 같은 sub-array로 선언 | [Key field는 값 하나입니다](#the-key-field-is-one-value) |
| shape이 `(1,)`인 NumPy field를 씀 | [원소가 하나인 vector](#one-element-vectors-are-stored-as-a-blob) (배포 순서가 중요합니다) |
| `AsyncQuery.foreach()`에 `async def` callback을 넘기거나, callback에서 thread-local 상태를 쓰거나, 취소 | [Async query](#async-queries) |
| `max_concurrent_operations`를 설정하고 `apply()`를 호출 | [`apply()`와 backpressure](#apply-counts-against-max_concurrent_operations) |
| 오래 실행되는 client 아래에서 Aerospike container를 재시작 | [Node 재시작](#node-restarts-with-a-new-node-id) |
| 0.14.x에 맞춰 memory 한도를 빠듯하게 잡음 | [Memory](#memory-under-concurrent-batch-load) |

`where()` predicate가 둘 이상인 query는 0.14.x와 마찬가지로 `InvalidArgError`를 발생시킵니다. [Query](#queries-take-one-where-predicate)를 참고하세요.

### 최소 server 버전 {#minimum-server-version}

0.15는 Aerospike Rust client 3.0을 기반으로 합니다(0.14.x는 2.2). Rust client 3.0에서 지원하는 최소 server 버전은 **6.4**입니다.

**대응:** 6.4보다 오래된 server는 client를 업그레이드하기 전에 먼저 업그레이드하세요. Integration test가 실행되는 server 버전은 [FAQ](/docs/faq#what-aerospike-server-versions-are-supported)에 있습니다.

### `operate_ordered()`: 연산마다 한 항목 {#operate_ordered-returns-one-entry-per-operation}

0.14.x의 `operate_ordered()`는 **bin**마다 항목 하나를 반환했습니다. 두 연산이 응답한 bin은 두 값을 담은 list로 한 번만 나타났고, 항목 순서도 연산 순서를 따르지 않았습니다(실행할 때마다 순서가 달라졌습니다). 0.15는 공식 Python client와 같은 결과를 반환합니다. 응답한 **연산**마다 `(bin, value)` 항목 하나를 요청 순서대로 돌려주며, 두 번 응답한 bin은 두 번 나타납니다.

```python
from aerospike_py import list_operations as lop
from aerospike_py import map_operations as mop

READ, INCR = aerospike_py.OPERATOR_READ, aerospike_py.OPERATOR_INCR
key = ("test", "demo", "ordered")


def ordered(initial, ops):
    client.put(key, initial, policy={"exists": aerospike_py.POLICY_EXISTS_REPLACE})
    return [tuple(b) for b in client.operate_ordered(key, ops).ordered_bins]


# 같은 bin을 두 번 읽기
print(ordered({"a": 1, "b": 2, "c": 3},
              [{"op": READ, "bin": "c"}, {"op": READ, "bin": "a"},
               {"op": READ, "bin": "c"}, {"op": READ, "bin": "b"}]))
# 같은 bin에 쓴 다음 읽기
print(ordered({"x": 2}, [{"op": INCR, "bin": "x", "val": 1}, {"op": READ, "bin": "x"}]))
print(ordered({"l": [1]}, [lop.list_append("l", 3), {"op": READ, "bin": "l"}]))
# 같은 요청에 map 연산을 추가
print(ordered({"x": 2, "m": {"k": 1}},
              [{"op": INCR, "bin": "x", "val": 1}, {"op": READ, "bin": "x"}, mop.map_size("m")]))
```

```text
# 0.14.x
[('c', [3, 3]), ('a', 1), ('b', 2)]
[('x', 3)]
[('l', [2, [1, 3]])]
[('x', 3), ('m', 1)]

# 0.15
[('c', 3), ('a', 1), ('c', 3), ('b', 2)]
[('x', 3)]
[('l', 2), ('l', [1, 3])]
[('x', None), ('x', 3), ('m', 1)]
```

**값이 없는 연산이 나타나는 경우.** Increment, write, 없는 bin 읽기는 값을 반환하지 않습니다. 이런 연산이 항목을 갖는지는 요청 전체에 따라 정해집니다.

- 요청에 **map, bit, HLL 연산**이 하나라도 있으면 bin을 지정한 모든 연산이 항목을 갖고, 값을 반환하지 않은 연산은 `(bin, None)`으로 나타납니다. `touch`는 생략되며 이 모드에서 `delete`의 결과는 `("", None)`입니다.
- 그 밖의 요청에는 값을 돌려준 연산이 나타납니다. 읽기 전용 list 요청에서는 nil 원소가 생략됩니다. 쓰기를 함께 요청하면 존재하는 list의 nil 원소는 `(bin, None)`으로 반환되고, 없는 list bin은 생략됩니다.

| 요청 (초기 record) | 0.15의 `ordered_bins` |
|---|---|
| `increment(x, 1)`, `read(x)` (`x=2`) | `[("x", 3)]` |
| `write(x, 7)` | `[]` |
| `read(missing)`, `read(b)` (`b=2`) | `[("b", 2)]` |
| `list_get(l, 0)`, `list_get(l, 1)` (`l=[None, 5]`) | `[("l", 5)]` |
| `write(x, 7)`, `map_size(m)` (`m`의 원소 1개) | `[("x", None), ("m", 1)]` |
| `read(missing)`, `map_size(m)` | `[("missing", None), ("m", 1)]` |
| `touch()`, `map_size(m)` | `[("m", 1)]` |
| `write(x, 7)`, `bit_count(b, 0, 8)` (`b=0x0f`) | `[("x", None), ("b", 4)]` |

`tests/compatibility/test_operate_ordered_contract.py`가 이 경우들을 포함한 여러 요청에서 binding의 결과를 공식 client의 결과와 비교합니다.

빈 bin 이름(공식 helper의 `read("")`)으로 읽으면 레코드 전체를 반환합니다. `MAP_RETURN_KEY_VALUE`의 ordered 결과는 `["j", 2, "k", 1]` 같은 평평한 리스트입니다. 일반 `operate()`는 기존처럼 key/value 튜플 리스트를 반환합니다.

**`operate()`는 바뀌지 않았습니다.** 여전히 bin마다 key 하나인 dict를 반환하고, 여러 연산이 같은 bin에 응답하면 list를, write에는 `None`을 넣지 않습니다.

```python
record = client.operate(key, [{"op": READ, "bin": "c"}, {"op": READ, "bin": "a"},
                              {"op": READ, "bin": "c"}, {"op": READ, "bin": "b"}])
print(record.bins)
```

```text
# 0.14.x
{'b': 2, 'c': [3, 3], 'a': 1}
# 0.15
{'c': [3, 3], 'a': 1, 'b': 2}
```

**대응:**

- Bin마다 값 하나가 필요하면 `operate()`를 사용하세요.
- `ordered_bins`를 위치로 읽는다면 위 규칙에 따라 위치를 다시 세세요.
- 두 번 응답한 bin을 list로 받고 싶다면 직접 모으세요: `[b.value for b in result.ordered_bins if b.name == "c"]`.
- 요청에 map, bit, HLL 연산이 있고 `(bin, None)` 항목이 필요 없다면 걸러 내세요: `[b for b in result.ordered_bins if b.value is not None]`.

### Query는 `where()` predicate를 하나만 받습니다 {#queries-take-one-where-predicate}

Query는 secondary-index predicate 하나로 실행됩니다. 같은 query에서 `where()`를 두 번 호출하면 query를 실행할 때(`results()`, `foreach()`, 순회) `InvalidArgError`가 발생합니다. 0.14.x도 같은 시점에 `InvalidArgError`를 발생시켰으므로 동작하던 코드는 영향을 받지 않고, 메시지만 바뀌었습니다.

```text
# 0.14.x
InvalidArgError: Invalid argument: Too many filter expressions
# 0.15
InvalidArgError: Invalid argument: a query takes at most one where() predicate, got 2
```

Rust client 3.0은 마지막 predicate 하나만 조용히 남기기 때문에 0.15가 직접 검사합니다. Query를 더 좁히려면 predicate는 하나만 두고 나머지 조건은 filter expression(`policy={"filter_expression": ...}`)으로 표현하세요.

### Batch 결과 {#batch-results}

#### `BatchRecord.result`의 의미

이제 `BatchRecord.result`는 다음과 같습니다.

- Server가 그 record의 성공을 알린 경우에만 `0`
- Server가 실패를 알린 경우 server의 result code(`2` not found, `27` filtered out, ...)
- 그 record에 대해 어떤 server도 응답하지 않은 경우 `-1`

0.14.x는 result code가 없는 row를 성공(`0`)으로 취급했기 때문에, 어떤 node도 응답하지 않은 record가 쓰인 것처럼 보일 수 있었습니다. `BatchRecord`에는 새 field `error_type`도 생겼습니다. 이 field는 실패의 종류를 이름으로 알려 주고, `-1`인 경우들을 서로 구분해 줍니다.

```python
from aerospike_py import exp

client.put(("test", "demo", "kept"), {"v": 1})
client.put(("test", "demo", "dropped"), {"v": 2})
keys = [
    ("test", "demo", "kept"),
    ("test", "demo", "dropped"),           # 아래 filter가 제외함
    ("test", "demo", "missing"),           # 쓴 적 없음
    ("no_such_namespace", "demo", "k"),    # cluster에 없는 namespace
]
only_v1 = {"filter_expression": exp.eq(exp.int_bin("v"), exp.int_val(1))}
for br in client.batch_read(keys, policy=only_v1).batch_records:
    print(br.result, getattr(br, "error_type", "(no field)"), br.in_doubt)
```

```text
# 0.14.x
0 (no field) False
27 (no field) False
2 (no field) False
11 (no field) False

# 0.15
0 None False
27 FilteredOut False
2 KeyNotFoundError False
20 InvalidNamespace False
```

Row의 결과를 구분하는 방법:

| 결과 | `result` | `error_type` | `in_doubt` |
|---|---|---|---|
| 성공 | `0` | `None` | `False` |
| Record 없음 | `2` | `"KeyNotFoundError"` | `False` |
| `filter_expression`으로 제외됨 | `27` | `"FilteredOut"` | `False` |
| Server가 알린 그 밖의 실패 | 해당 code | code 이름. 예: `"KeyExistsError"`, `"GenerationError"`, `"DeviceOverload"` | `False` |
| Server가 timeout을 알림 | `9` | `"ServerTimeout"` | write면 `True`: master가 이미 적용했을 수 있음 |
| 요청을 보냈지만 client가 기다리기를 멈춤 | `-1` | `"Timeout"` | write면 `True` |
| 전송 실패 | `-1` | `"Connection"`, `"InvalidNode"`, ... | 이미 보낸 write면 `True` |
| 그 record에 대해 어떤 node도 응답하지 않음 | `-1` | `"NoResponse"` | 아무것도 보내지 않았으면(key를 route하지 못함) `False`. 호출이 row를 돌려받지 못한 채 끝났고 이미 보냈을 수 있으면 write에 대해 `True` |

`in_doubt`는 record가 실패했지만 write가 적용되었을 수도 있다는 뜻입니다. 요청은 보냈는데 응답이 돌아오지 않은 경우입니다. 다시 쓰기 전에 record를 읽어 확인하세요.

Server가 retry할 만한 code인 `KEY_BUSY`(14), `DEVICE_OVERLOAD`(18), `PARTITION_UNAVAILABLE`(11)로 거절한 write는 응답입니다. 그 row는 해당 code와 `in_doubt == False`를 갖고, key가 하나뿐인 batch에서도 호출은 정상적으로 반환됩니다. 0.14.x와 같습니다. Write batch를 `max_retries > 0`으로 보내면 결과 네 가지가 더 in doubt로 보고됩니다. [두 번째 전송이 응답했을 수 있는 row](#rows-a-second-send-may-have-answered)를 참고하세요.

#### 다섯 번째 field: `error_type`

이제 `BatchRecord`는 field가 다섯 개인 named tuple입니다: `key`, `result`, `record`, `in_doubt`, `error_type`. 정확히 이름 네 개로 unpack하는 코드는 깨집니다.

```python
br = client.batch_write([(("test", "demo", "kept"), {"v": 1})]).batch_records[0]
key, result, record, in_doubt = br
```

```text
# 0.14.x
(오류 없음)
# 0.15
ValueError: too many values to unpack (expected 4)
```

**대응:** attribute(`br.result`, `br.in_doubt`, `br.error_type`)로 접근하거나 이름 다섯 개로 unpack하세요.

#### 전체가 실패한 batch 호출도 row를 남깁니다 {#a-batch-call-that-fails-as-a-whole-keeps-its-rows}

전체가 실패한 batch 호출은 여전히 exception을 발생시키지만, 이제 exception이 row를 담고 있습니다. `exc.partial_result`는 요청한 record마다 `BatchRecord` 하나를 요청 순서대로 담은 `BatchWriteResult`입니다. 다른 node가 응답한 record는 결과를 그대로 갖고, 나머지는 결과가 없는 이유를 알려 줍니다. 모든 batch method에 적용됩니다: `batch_read`, `batch_write`, `batch_write_numpy`, `batch_operate`, `batch_remove`, `batch_apply`. 그 밖의 실패에서는 `partial_result`가 `None`입니다.

```python
keys = [("no_such_namespace", "demo", f"k{i}") for i in range(3)]
try:
    client.batch_write([(k, {"v": 1}) for k in keys])
except aerospike_py.AerospikeError as exc:
    print(type(exc).__name__)
    partial = getattr(exc, "partial_result", None)
    if partial is not None:
        for br in partial.batch_records:
            print(br.key.user_key, br.result, br.error_type, br.in_doubt)
```

```text
# 0.14.x
ClusterError

# 0.15
InvalidArgError
k0 -1 NoResponse False
k1 -1 NoResponse False
k2 -1 NoResponse False
```

이 경우 exception class도 바뀌었습니다. [없는 namespace](#an-unknown-namespace-raises-invalidargerror)를 참고하세요. `batch_write(retry=N)`이 exception을 발생시키면 `exc.partial_result.retry`에 그 호출의 retry counter가 들어 있습니다.

`partial_result`의 row 중 하나라도 in doubt이면 exception도 `in_doubt == True`입니다. 호출이 여러 node에서 실패했다면 exception은 그중 한 node의 오류(몫이 처음 실패한 node)이므로, exception의 type과 `result_code`는 record 순서에 따라 달라질 수 있습니다. 각 record에 무슨 일이 있었는지는 row가 알려 줍니다.

**대응:** 실패한 batch 호출을 catch하는 곳에서는 무엇을 다시 보낼지 정하기 전에 `exc.partial_result`를 확인하세요. `result == 0`인 row는 쓰였고, `in_doubt`인 row는 쓰였을 수도 있습니다.

```python
try:
    client.batch_write(records)
except aerospike_py.AerospikeError as exc:
    if exc.partial_result is None:
        raise
    done = [br.key for br in exc.partial_result.batch_records if br.result == 0]
    unsure = [br.key for br in exc.partial_result.batch_records if br.in_doubt]
```

### Write batch는 더 이상 자동으로 retry하지 않습니다 {#write-batches-no-longer-retry-automatically}

0.14.x에서는 모든 batch 호출이 `max_retries = 2`인 policy에서 시작했습니다. Batch의 응답이 유실되면 Rust client가 최대 두 번까지 다시 보냈고, increment와 UDF 호출도 예외가 아니었으며, server는 보낸 만큼 적용했습니다. 0.15에서는 batch가 하는 일에 따라 기본값이 정해집니다.

| Batch | 기본 `max_retries` |
|---|---|
| `batch_read`, 그리고 연산이 모두 읽기인 `batch_operate` | `2` (변경 없음) |
| `batch_write`, `batch_write_numpy`, `batch_remove`, `batch_apply`, 그리고 write가 있는 `batch_operate` | `0` |

쓰기 배치에서 양수 `max_retries`와 `POLICY_REPLICA_MASTER`를 함께 지정하면 전송 전에 거부합니다. 같은 노드에 재전송하면 이미 응답을 받은 행도 중복 실행될 수 있기 때문입니다.

아래 예제는 실행 횟수를 직접 세고 socket timeout보다 오래 걸리는 UDF를 사용합니다. 그래서 server가 아직 실행하는 동안 client가 기다리기를 멈춥니다.

```lua
-- slow_count.lua
function run(rec, rounds)
    local total = 0
    for i = 1, rounds do
        total = total + (i % 7)
    end
    if rec['runs'] == nil then
        rec['runs'] = 1
    else
        rec['runs'] = rec['runs'] + 1
    end
    aerospike:update(rec)
    return rec['runs']
end
```

```python
import time

client.udf_put("slow_count.lua")
key = ("test", "demo", "counter")
client.put(key, {"v": 1})
policy = {"total_timeout": 0, "socket_timeout": 50}
try:
    client.batch_apply([key], "slow_count", "run", [10_000_000], policy=policy)
except aerospike_py.AerospikeError as exc:
    print(type(exc).__name__)
time.sleep(4)  # server가 받은 실행을 모두 끝낼 때까지 대기
print("runs:", client.get(key).bins["runs"])
```

```text
# 0.14.x
ClientError
runs: 3

# 0.15
AerospikeTimeoutError
runs: 1
```

**대응:** write batch를 client가 다시 보내야 한다면 직접 요청하세요: `policy={"max_retries": 2}`. 0.15에서 이 policy로 같은 예제를 실행하면 `runs: 3`이 출력됩니다. Batch를 두 번 적용해도 한 번 적용한 것과 결과가 같을 때만 이렇게 하세요. `CREATE_ONLY`나 generation 검사가 없는 전체 record `batch_write`, `batch_remove`, 읽기가 이에 해당합니다. Increment, append, 원소를 추가하는 list·map 변경, 대부분의 UDF, `CREATE_ONLY` write(이미 적용된 write인데 두 번째 사본이 "record exists"로 실패), generation 검사가 있는 write에는 쓰지 마세요. `batch_write`와 `batch_write_numpy`에는 아래에서 설명하는 `retry=N`을 권장합니다.

#### 두 번째 전송이 응답했을 수 있는 row {#rows-a-second-send-may-have-answered}

Write에 `max_retries > 0`을 주면, 응답이 유실되었을 때 Rust client가 batch 중 한 node 몫을 다시 보냅니다. 첫 전송이 이미 적용되었다면 두 번째 전송은 자기가 한 일을 만납니다. 다시 보낸 delete는 record를 찾지 못하고, 다시 보낸 filter 있는 write는 더 이상 조건에 맞지 않으며, 다시 보낸 UDF는 첫 실행이 남긴 상태 때문에 실패합니다. Rust client는 row가 두 번 전송되었는지 알려 주지 않으므로, `batch_write`, write가 있는 `batch_operate`, `batch_remove`, `batch_apply`의 row가 `KEY_NOT_FOUND`(2), `FILTERED_OUT`(27), `UDF_BAD_RESPONSE`(100)로 끝나면 `in_doubt == True`로 보고됩니다. 호출이 record를 바꿨는지 알 수 없다는 뜻입니다. Node 몫을 다시 보낼 때가 되었는데 그 record의 node를 찾지 못해(그사이 node가 cluster에서 빠졌거나 client가 닫힘) client가 직접 `PARTITION_UNAVAILABLE`(11)을 준 row도 마찬가지입니다. 첫 전송이 적용되었을 수 있기 때문입니다. 이런 row가 있어도 호출은 정상적으로 반환됩니다. 첫 전송에서 server가 `PARTITION_UNAVAILABLE`로 거절한 row는 그대로 `in_doubt == False`입니다. 이런 policy에서 `RecordNotFound`를 발생시킨 `remove()`도 `in_doubt == True`를 갖습니다.

기본 policy(모든 write에서 `max_retries`는 `0`)에서는 아무것도 바뀌지 않고, 읽기(`batch_read`)는 결코 in doubt가 아닙니다. 예제는 [Error Handling](/docs/guides/error-handling#re-sent-writes-and-in_doubt)에 있습니다.

#### `batch_write`의 `retry` 인자 {#the-retry-argument-of-batch_write}

`batch_write(records, retry=N)`과 `batch_write_numpy(..., retry=N)`은 binding 자체의 retry loop를 실행합니다. 0.15의 동작은 다음과 같습니다.

- Exponential backoff(full jitter, 시도 사이 최대 500 ms)로 최대 `N + 1`번 시도합니다.
- Transient error로 실패한 record만 다시 보냅니다: timeout, device overload, key busy, 끊어진 connection, 내려간 node.
- 이미 성공한 record는 절대 다시 보내지 않습니다.
- 앞선 쓰기가 적용되었을 수 있고 필터, generation 검사, `CREATE_ONLY`, 명시적인 상대 TTL을 사용하거나 모든 bin 값이 `None`이면 해당 row는 `in_doubt = True`를 유지합니다. 마지막 bin을 지우면 레코드도 삭제되므로 다시 보내면 성공한 삭제를 레코드 없음으로 보고할 수 있습니다.
- 다시 해도 똑같이 실패할 오류(없는 namespace, 잘못된 인자)는 다시 시도하지 않습니다.
- `total_timeout`(기본값 1000 ms)이 다 되면 멈춥니다. 실제로 `N + 1`번 시도하려면 `policy={"total_timeout": 30000}`처럼 늘리세요.

`result.retry`(`BatchRetryInfo`)는 `attempts`, `max_attempts`, `truncated_by_timeout`, `unresolved`를 알려 줍니다. 호출이 exception을 발생시키면 같은 counter가 `exc.partial_result.retry`에 들어 있습니다.

`retry=N`과 `policy["max_retries"]`는 안팎으로 겹친 두 loop입니다. `N + 1`번의 시도가 각각, 그 record가 성공했는지와 상관없이, 그 아래에서 `max_retries`번씩 다시 보내집니다. 이제 둘을 함께 주면 `InvalidArgError`가 발생합니다. `max_retries`를 명시적으로 `0`으로 주는 것은 허용됩니다.

```python
records = [(("test", "demo", f"r{i}"), {"v": i}) for i in range(3)]
try:
    result = client.batch_write(records, policy={"max_retries": 1}, retry=2)
    print([br.result for br in result.batch_records])
except aerospike_py.InvalidArgError as exc:
    print(exc)
```

```text
# 0.14.x
[0, 0, 0]

# 0.15
retry=2 and policy['max_retries']=1 were both given; they would multiply into up to 6 sends per record. Use retry= alone: it re-sends only the records that failed.
```

**대응:** `retry=N`을 넘기는 `batch_write`·`batch_write_numpy` 호출에서 `max_retries`를 제거하세요.

### Exception {#exceptions}

#### 모든 exception이 무슨 일이 있었는지 알려 줍니다

모든 `AerospikeError`에 attribute 네 개가 있습니다. 0.14.x에는 `result_code`만 있었습니다.

| Attribute | 의미 |
|---|---|
| `result_code` | Server가 응답했으면 server의 result code, 어떤 server도 응답하지 않았으면 `-1`. |
| `error_type` | 실패의 종류를 나타내는 이름. Server code는 code 이름을 따릅니다(`"KeyNotFoundError"`, `"KeyExistsError"`, `"GenerationError"`, `"FilteredOut"`, `"DeviceOverload"`, ...; server가 알린 timeout은 `"ServerTimeout"`). Client 쪽 실패는 `"Timeout"`, `"MaxRetriesExceeded"`, `"Connection"`, `"NoMoreConnections"`, `"MaxErrorRate"`, `"InvalidNode"`, `"InvalidArgument"`, `"UdfBadResponse"`, `"StreamTerminated"`, `"BadResponse"`, `"Backpressure"`, `"RustPanic"`, `"Client"` 중 하나입니다. |
| `in_doubt` | Write를 보냈지만 확정된 응답을 받지 못해 server가 적용했을 수 있으면 `True`. server가 실패라고 응답한 경우(record 존재, UDF 실패 등)와 읽기에서는 항상 `False`. `max_retries > 0`으로 보낸 write는 예외입니다. [두 번째 전송이 응답했을 수 있는 row](#rows-a-second-send-may-have-answered)를 참고하세요. 전체가 실패한 batch 호출의 exception은 row 중 하나라도 in doubt이면 in doubt입니다. |
| `partial_result` | 전체가 실패한 batch 호출의 row. 그 밖에는 `None`. [위](#a-batch-call-that-fails-as-a-whole-keeps-its-rows)를 참고하세요. |

`result_code == -1`은 여러 실패를 포함하며, `error_type`으로 구분합니다. 두 가지 실패에서는 exception class와 `error_type`이 바뀌었습니다.

```python
def describe(call):
    try:
        call()
    except aerospike_py.AerospikeError as exc:
        print(type(exc).__name__, exc.result_code, getattr(exc, "error_type", "(no attribute)"))


describe(lambda: client.get(("test", "demo", "never_written")))
describe(lambda: client.apply(key, "no_such_module", "no_such_function", []))
describe(lambda: client.get(("no_such_namespace", "demo", "k")))
```

```text
# 0.14.x
RecordNotFound 2 (no attribute)
ClientError -1 (no attribute)
AerospikeTimeoutError -1 (no attribute)

# 0.15
RecordNotFound 2 KeyNotFoundError
UDFError 100 UdfBadResponse
InvalidArgError -1 InvalidArgument
```

#### 실패한 UDF는 `UDFError`를 발생시킵니다

0.14.x에서 server가 실행하지 못한 UDF는 `result_code == -1`인 일반 `ClientError`를 발생시켰고, aerospike-py의 bug일 수 있다는 log도 남겼습니다. 0.15에서는 `result_code == 100`(`AEROSPIKE_ERR_UDF`)인 `UDFError`(`ServerError`의 하위 class)를 발생시킵니다. 실패한 `batch_apply` row가 원래부터 알리던 code와 같습니다.

UDF 실패는 응답을 잃은 것이 아니라 server가 보낸 응답입니다. server가 함수를 찾지 못했거나, 실행한 뒤 record를 되돌리고 실패했다고 알린 것입니다. 그래서 `apply()`에서도 `batch_apply` row에서도 `exc.in_doubt`는 `False`입니다(batch를 `max_retries > 0`으로 보낸 경우는 예외입니다. [두 번째 전송이 응답했을 수 있는 row](#rows-a-second-send-may-have-answered)를 참고하세요). client가 기다리다 포기한 UDF 호출은 timeout이며, 이 경우는 in doubt입니다.

**대응:** `apply()` 주변에서는 `aerospike_py.UDFError`(또는 `ServerError`)를 catch하세요. `except ClientError`는 더 이상 UDF 실패를 잡지 않습니다.

#### 없는 namespace는 `InvalidArgError`를 발생시킵니다 {#an-unknown-namespace-raises-invalidargerror}

Cluster에 없는 namespace의 key는 0.14.x에서 단일 record 명령이면 `AerospikeTimeoutError`, batch 호출이면 `ClusterError`를 발생시켰습니다. 이제 둘 다 `InvalidArgError`(`result_code == -1`, `error_type == "InvalidArgument"`)를 발생시킵니다. 다른 key는 보낼 수 있어서 batch 호출이 반환되는 경우, 그런 key의 row는 `result == 20`, `error_type == "InvalidNamespace"`를 갖습니다(0.14.x: `11`).

**대응:** 잘못 입력했거나 없는 namespace를 처리하려고 `ClusterError`나 `AerospikeTimeoutError`를 catch했다면 `InvalidArgError`를 catch하세요.

#### Metric도 같은 이름을 씁니다

`db_client_operation_duration_seconds`의 Prometheus `error_type` label과 OpenTelemetry `error.type` attribute는 `exc.error_type`과 같은 분류에서 나옵니다. 그래서 dashboard와 `except` 절이 같은 실패를 같은 이름으로 부릅니다.

```text
db_client_operation_duration_seconds_count{...,db_operation_name="get",error_type="KeyNotFoundError"} 1
```

#### 메시지가 바뀌었습니다

여러 exception 메시지의 문구가 바뀌었습니다. 예를 들어 0.14.x의 `AEROSPIKE_ERR (2): Server error: KeyNotFoundError, In Doubt: false, Node: ...`는 이제 `AEROSPIKE_ERR (2): Key not found [node=...]`입니다. 메시지 문자열로 분기하지 말고 exception class, `result_code`, `error_type`을 사용하세요.

### Policy 값을 검사합니다 {#policy-values-are-checked}

`exists`, `gen`, `commit_level`, `replica`, `read_mode_ap`, `expected_duration` 값이 `POLICY_*` / `QUERY_DURATION_*` 상수 중 하나가 아니면, 이제 아무것도 보내기 전에 `InvalidArgError`가 발생합니다. 0.14.x에서는 알 수 없는 값이 기본값으로 바뀌었습니다. `exists=9`는 일반 update가 되었고, `gen=9`는 generation 검사를 꺼 버렸습니다.

```python
try:
    client.put(key, {"v": 2}, policy={"exists": 9})
    print("written:", client.get(key).bins)
except aerospike_py.InvalidArgError as exc:
    print(exc)
```

```text
# 0.14.x
written: {'v': 2}

# 0.15
invalid exists value: 9 (valid: POLICY_EXISTS_IGNORE=0, POLICY_EXISTS_UPDATE_ONLY=1, POLICY_EXISTS_REPLACE=2, POLICY_EXISTS_REPLACE_ONLY=3, POLICY_EXISTS_CREATE_ONLY=4)
```

**대응:** `aerospike_py.POLICY_EXISTS_CREATE_ONLY`처럼 상수를 사용하세요.

#### Expression이 아닌 `filter_expression`은 거부됩니다 {#a-filter_expression-that-is-not-an-expression-is-refused}

`aerospike_py.exp`로 만든 expression이 아닌 `filter_expression`(문자열, 숫자, list, dict)은 이제 아무것도 보내기 전에 `InvalidArgError`를 발생시킵니다: `filter_expression must be an expression built with aerospike_py.exp, got str`. 0.14.x까지는 이런 값을 아무 말 없이 버리고 **filter 없이** 호출을 실행했습니다. `client.put(key, bins, policy={"filter_expression": "v == 1"})`은 record를 조건 없이 썼습니다. `None`은 여전히 "filter 없음"을 뜻합니다.

**대응:** `exp.eq(exp.int_bin("v"), exp.int_val(1))`처럼 `aerospike_py.exp`로 filter를 만드세요. 여기서 exception이 발생하는 호출은 0.14.x에서 filter 없이 실행되었으니, 그 호출이 쓰거나 반환한 것을 확인하세요.

#### 아무것도 보내기 전에 거부되는 그 밖의 값

- `max_retries = 2**64 - 1`은 `InvalidArgError`(`max_retries is too large: ...`)를 발생시킵니다. Rust client 3.0은 이 값으로는 한 번도 시도하지 않으므로, 그대로 두면 호출이 보내지지도 않은 채 "Timeout after 0 tries"로 실패합니다.
- Field에 맞지 않는 정수(`retry=-1`, `total_timeout=-1`, `ttl=2**70`)는 `OverflowError`를 발생시킵니다. aerospike-py의 bug일 수 있다는 log는 남기지 않습니다.
- `2**61 - 1`보다 큰 `record_queue_size`는 `InvalidArgError`(`record_queue_size is too large: ...`)를 발생시킵니다. 0.14.x에서는 client가 queue를 할당할 수 없는 값(예: `2**60`)이 `RustPanicError`를 발생시켰습니다.
- Bin이 없는 `batch_write()` record `(key, {})`는 `InvalidArgError`(`record 1 has no bins: ...`)를 발생시키고 아무것도 쓰지 않습니다. 0.14.x에서는 호출이 `ClientError`("Batch write operations do not contain a write")를 발생시키고 aerospike-py의 bug일 수 있다는 log를 남겼습니다. Bin을 `None`으로 지정하는 것은 여전히 write이며, 그 bin을 제거합니다. `batch_write_numpy()`도 같은 이유로 bin field가 없는 dtype을 `ValueError`로 거부합니다.

`batch_write(retry=2**32 - 1)`은 `retry.max_attempts == 2**32 - 1`을 알려 줍니다. 횟수가 `0`으로 넘어가지 않고 최댓값에서 멈춥니다.

### 언어별 blob이 담긴 record를 읽을 수 있습니다 {#records-with-a-language-specific-blob-are-readable}

예전 client는 Aerospike type이 없는 값을 자기 언어의 serializer로 직렬화해 고유한 particle type으로 저장했습니다: `JAVA_BLOB`(7), `CSHARP_BLOB`(8), `PYTHON_BLOB`(9, pickle), `RUBY_BLOB`(10), `PHP_BLOB`(11), `ERLANG_BLOB`(12). 오래 운영된 cluster에는 이런 record가 아직 남아 있습니다. 0.14.x에서는 이런 bin이 있는 record를 읽기만 해도 `RustPanicError`가 발생해 record 전체를 읽을 수 없었습니다. 0.15에서는 그 bin을 raw payload를 담은 `bytes`로 반환하고, 나머지 bin은 평소대로 읽으며, type마다 처음 만난 값만 warning으로 남깁니다(그 뒤로는 debug level이라, 오래된 data를 scan해도 log가 넘치지 않습니다). `get()`, `batch_read()`, scan 모두 이렇게 동작합니다(issue #280).

```python
import logging
import pickle

logging.basicConfig(level=logging.WARNING)
key = ("test", "demo", "legacy")  # 예전 client가 씀: plain=7, legacy=PYTHON_BLOB
try:
    record = client.get(key)
    print(record.bins["plain"], type(record.bins["legacy"]).__name__)
    print(pickle.loads(record.bins["legacy"]))  # 신뢰할 수 있는 데이터에만 사용
except aerospike_py.RustPanicError as exc:
    print(f"{type(exc).__name__}: {exc}")
```

```text
# 0.14.x (aerospike-py의 bug일 수 있다는 error log 뒤에)
RustPanicError: Rust panic in `Client.get`: internal error: entered unreachable code

# 0.15
WARNING:_aerospike::types::value:bin value has particle type 9, which this client does not interpret; returning its 26 raw bytes (further values of this type are logged at debug level)
7 bytes
{'answer': 42}
```

`put()`으로 이 bytes를 다시 쓰면 일반 blob으로 저장되고, 그 뒤에 그 bin을 읽을 때는 warning이 남지 않습니다.

**대응:** 이런 record를 건너뛰려고 `RustPanicError`를 catch하던 코드는 이제 record를 받습니다. 값이 필요하면 bytes를 직접 decode하세요. `PYTHON_BLOB`이라면 `pickle.loads(...)`이며, 신뢰할 수 있는 데이터에만 사용하세요. Unpickling은 코드를 실행할 수 있습니다.

### NumPy batch 읽기와 쓰기 {#numpy-batch-reads-and-writes}

아래 규칙은 sync client와 async client에 똑같이 적용됩니다.

#### `batch_write_numpy()`는 array에서 layout을 읽습니다

이제 signature는 `batch_write_numpy(data, namespace, set_name, _dtype=None, key_field="_key", policy=None, retry=0)`입니다. Layout은 `data.dtype`에서 가져옵니다. 0.14.x에서는 `_dtype`이 필수였고, array와 맞지 않아도 array의 byte를 그 dtype으로 읽었습니다. 0.15에서는 `data.dtype`과 다른 `_dtype`을 주면 첫 row를 보내기 전에 `ValueError`가 발생합니다.

```python
import numpy as np

dtype = np.dtype([("_key", "i8"), ("score", "f8"), ("count", "i4")])
data = np.array([(101, 0.5, 1), (102, 1.5, 2)], dtype=dtype)
wrong = np.dtype([("_key", "i8"), ("score", "f4"), ("count", "i4")])  # f8이 아닌 f4
try:
    result = client.batch_write_numpy(data, "test", "demo", wrong)
    print([(br.key.user_key, br.result) for br in result.batch_records])
except ValueError as exc:
    print(exc)
```

```text
# 0.14.x (두 번째 row는 잘못 읽은 byte로 만든 key로 쓰였습니다)
[(101, 0), (438086664193, 0)]

# 0.15
_dtype does not match the array: data.dtype is [('_key', '<i8'), ('score', '<f8'), ('count', '<i4')], _dtype is [('_key', '<i8'), ('score', '<f4'), ('count', '<i4')]. Omit _dtype to use data.dtype, or convert the array first with data.astype(_dtype).
```

Row는 `numpy.asarray(data)`에서 읽습니다. `numpy.recarray` 같은 array subclass는 그 바탕의 일반 array로 쓰이고, masked array의 mask는 무시됩니다.

**대응:** 넘기는 dtype이 `data.dtype`이라면 고칠 것이 없습니다. 그렇지 않다면 인자를 빼거나, 먼저 `data.astype(...)`으로 array를 변환하세요.

#### dtype을 양방향에서 검사합니다

`batch_write_numpy()`와 `to_numpy()`는 데이터를 쓰거나 채우기 전에 dtype을 검사합니다. `to_numpy(dtype)`은 `numpy.dtype(...)`이 받는 것은 무엇이든 받으며, NumPy가 그로부터 만든 dtype대로 row를 배치합니다. 두 method는 무엇이든 쓰거나 채우기 전에 다음을 거부합니다.

- Named field가 없는 array나 dtype (`TypeError`)
- NumPy의 가변 길이 `StringDType` (`TypeError`)
- `U`, `O` field와 structured field 안에 중첩된 object member (`TypeError`)
- Native가 아닌 byte order의 field (`ValueError`, 0.14.x와 같음)
- 지원하지 않는 원소 크기

크기가 0보다 큰 출력 필드의 바이트 구간이 겹치면 `ValueError`가 발생합니다. 누락된 bin의 필드를 0으로 유지하려면 각 bin에 독립된 저장 공간이 필요합니다. `batch_write_numpy()`의 입력 필드는 계속 겹칠 수 있습니다.

0.14.x에서는 structured field 안에 중첩된 object member가 object pointer의 raw byte 그대로 server에 쓰였습니다.

```text
# 0.14.x: ("s", [("x", "i4"), ("o", "O")])로 batch_write_numpy한 뒤 저장된 bin
{'s': b'\x00\x00\x00\x00H\xf7\xf8\x02\x01\x00\x00\x00'}
# 0.15
TypeError: dtype field 's' holds Python objects ([('x', '<i4'), ('o', 'O')]): an object member nested inside a structured ...
```

#### Key field는 값 하나입니다 {#the-key-field-is-one-value}

`batch_write_numpy()`의 key field(`_key`, 또는 `key_field`로 지정한 field)는 값 하나, 즉 scalar 정수이거나 고정 폭 bytes field여야 합니다. 원소가 하나인 `("_key", "i8", (1,))`를 포함한 sub-array나 중첩된 structured field는 무엇이든 쓰기 전에 `TypeError`를 발생시킵니다: `the key field '_key' must be a scalar integer or bytes field, not a sub-array or a nested structure; ...`. 0.14.x는 `("_key", "i8", (1,))`를 받아들여 정수 key로 썼습니다.

**대응:** key를 `("_key", "i8")`로 선언하세요. Sub-array **bin** field는 영향을 받지 않습니다. 이들은 vector이며 blob으로 저장됩니다([원소가 하나인 vector](#one-element-vectors-are-stored-as-a-blob) 참고).

#### Vector 길이와 float 범위

숫자 sub-array field는 vector입니다. 읽을 때는 field 크기와 정확히 같은 byte 수의 blob만 받고, 다른 길이는 오류입니다. Scalar는 원소가 하나인 field만 채울 수 있습니다. `f2`나 `f4` field에 담기에 너무 큰 유한값은 `OverflowError`를 발생시키고, NaN과 무한대는 그대로 유지됩니다. 0.14.x에서는 짧은 blob은 0으로 채우고, 긴 blob은 잘라 내고, scalar는 더 긴 vector의 첫 원소만 채웠으며, 넘치는 값은 `inf`가 되었습니다. 모두 오류 없이 일어났습니다. 고정 폭 bytes field(`S<N>`)의 padding·잘라 내기 규칙은 그대로입니다.

```python
client.put(("test", "demo", 121), {"short": b"\x00" * 8, "scalar": 1.5, "big": 70000.0})
handle = client.batch_read([("test", "demo", 121)])
for field in [("short", "f8", (4,)), ("scalar", "f8", (4,)), ("big", "f2")]:
    try:
        print(handle.to_numpy(np.dtype([field])).batch_records.tolist())
    except (ValueError, OverflowError) as exc:
        print(f"{type(exc).__name__}: {exc}")
```

```text
# 0.14.x
[(array([0., 0., 0., 0.]),)]
[(array([1.5, 0. , 0. , 0. ]),)]
[(inf,)]

# 0.15
ValueError: vector length mismatch for field 'short': the stored blob has 8 bytes, the dtype expects 32 (4 elements of 8 bytes)
ValueError: vector length mismatch for field 'scalar': the stored value is a scalar, the dtype expects 4 elements
OverflowError: float overflow: value 70000 does not fit in f16 for field 'big'
```

**대응:** 읽는 dtype을 저장된 값에 맞추세요. Bin에 실제로 길이가 다른 값이 섞여 있다면 `to_numpy()` 없이 읽으세요.

#### 원소가 하나인 vector는 blob으로 저장됩니다 {#one-element-vectors-are-stored-as-a-blob}

:::danger[shape `(1,)` field: reader를 먼저 업그레이드하세요. writer를 바꾼 뒤에는 0.14.x로 되돌릴 수 없습니다]

0.15는 shape이 `(1,)`인 sub-array field(예: `("score", "f4", (1,))`)를 다른 vector와 마찬가지로 field 크기의 **blob**으로 씁니다. 0.14.x는 이를 **scalar**로 썼습니다. Server에 저장되는 type이 바뀝니다.

- 0.15는 둘 다 읽습니다. 0.14.x가 쓴 scalar는 `(1,)` field에 길이 1인 vector로 읽힙니다.
- 0.14.x는 blob을 읽지 못합니다. `to_numpy()`가 batch 전체에 대해 `TypeError`를 발생시킵니다.

따라서 `(1,)` field로 쓰는 bin마다 다음 순서를 지키세요.

1. 그 bin을 읽는 **모든 reader**를 먼저 0.15로 업그레이드합니다.
2. 그다음 **writer**를 업그레이드합니다.
3. 0.15 writer가 그런 bin을 한 번이라도 쓴 뒤에는 **0.14.x로 되돌릴 수 없습니다**. 0.14.x reader는 blob을 거부합니다.

Reader를 모두 먼저 업그레이드할 수 없다면, writer에서 field를 scalar로 선언하세요(`("score", "f4", (1,))` 대신 `("score", "f4")`). 0.15는 이를 scalar로 저장하고, 두 버전 모두 `(1,)` field로 읽을 수 있습니다.

:::

```python
dtype = np.dtype([("_key", "i8"), ("score", "f4", (1,))])
client.batch_write_numpy(np.array([(401, [1.5])], dtype=dtype), "test", "demo", dtype)
print(client.get(("test", "demo", 401)).bins)
```

```text
# 0.14.x가 쓴 경우
{'score': 1.5}
# 0.15가 쓴 경우
{'score': b'\x00\x00\xc0?'}
```

```python
rows = client.batch_read([("test", "demo", 401)]).to_numpy(np.dtype([("score", "f4", (1,))]))
print(rows.batch_records.tolist())
```

```text
# 0.14.x가 0.15가 쓴 record를 읽는 경우
TypeError: cannot write bytes to numeric field 'score'
# 0.15가 둘 중 어느 record를 읽어도
[(array([1.5], dtype=float32),)]
```

#### `NumpyBatchRecords`의 row와 key

결과의 row `i`는 이전과 같이 hit이든 miss든 요청 `i`에 대응합니다. `get()`과 `in`이 쓰는 key index에는 실제 user key만 들어갑니다. 0.14.x에서는 digest만으로 요청한 row가 지어낸 key로 index되었습니다(native 변환에서는 `"__no_user_key_<i>__"`, 순수 Python 변환에서는 row 번호 `i`이며, 후자는 그 번호와 같은 실제 정수 key를 가릴 수 있었습니다). 이제 그런 row는 위치로만 접근할 수 있습니다. 두 번 요청한 user key는 이전과 같이 마지막 row를 가리킵니다.

```python
client.put(("test", "demo", 0), {"v": 1000})
client.put(("test", "demo", 611), {"v": 1611})
digest = client.batch_read([("test", "demo", 611)]).batch_records[0].key[3]
result = client.batch_read([("test", "demo", None, digest), ("test", "demo", 0)]).to_numpy(
    np.dtype([("v", "i8")])
)
print(result.batch_records["v"].tolist(), "__no_user_key_0__" in result, result.get(0)["v"])
```

```text
# 0.14.x
[1611, 1000] True 1000
# 0.15
[1611, 1000] False 1000
```

#### `batch_read()` handle의 길이

`batch_read()`가 반환하는 `LazyBatchRecords`의 `len(handle)`은 이제 mapping에 있는 서로 다른 key의 수이므로 항상 `len(handle.to_dict())`와 같습니다. 0.14.x에서는 user key가 있는 성공 row 수를 셌기 때문에, 같은 key를 두 번 요청하거나 두 set에서 요청하면 값이 너무 컸습니다. `found_count()`는 이전과 같이 성공 row 수를 세고, `to_list()`는 요청마다 slot 하나를 갖습니다.

```python
client.put(("test", "demo", "a"), {"v": 1})
client.put(("test", "demo", "b"), {"v": 2})
handle = client.batch_read([("test", "demo", "a"), ("test", "demo", "a"), ("test", "demo", "b")])
print(len(handle), len(handle.to_dict()), handle.found_count(), len(handle.to_list()))
```

```text
# 0.14.x
3 2 3 3
# 0.15
2 2 3 3
```

`to_dict()`는 얕은 복사본을 반환합니다. 바깥 dict는 새것이지만 안의 bins dict는 handle과 공유합니다. Bins dict를 바꾸기 전에 복사하거나, 호출할 때마다 새 dict를 만드는 `to_list()`를 사용하세요.

**대응:** "몇 개의 record가 돌아왔는가"에는 `found_count()`를, "mapping에 key가 몇 개인가"에는 `len(handle)`을 사용하세요.

### Async query {#async-queries}

#### Query를 취소하면 멈춥니다

`AsyncQuery.results()`와 `AsyncQuery.foreach()`는 이전에 worker thread에서 query를 실행했습니다. Task를 취소하면 `CancelledError`는 바로 발생했지만, thread는 scan이 끝날 때까지 record를 읽고 callback을 계속 호출했습니다. 0.15에서는 둘 다 query의 record stream을 await하며 읽으므로, task를 취소하면 client와 server 양쪽에서 query가 멈춥니다.

`foreach()`는 여전히 worker thread에서 callback을 호출하므로 callback이 block되어도 됩니다. Callback은 서로 겹쳐 실행되지 않지만 모두 같은 thread에서 실행되지는 않습니다. Event loop의 기본 executor가 record 묶음마다 thread를 고르므로, thread-local에 상태를 두지 마세요. Callback이 발생시킨 exception은 query를 멈추고 `foreach()`에서 그대로 다시 발생합니다. `StopIteration`만은 coroutine을 빠져나갈 때 Python이 하듯 `StopIteration`을 `__cause__`로 가진 `RuntimeError`로 전달됩니다. Task가 취소되면 실행 중인 callback은 끝까지 실행되고, 새 callback은 시작되지 않으며, 그다음에야 `CancelledError`가 발생합니다. `asyncio.run`이 Ctrl-C에서 하듯 모든 task를 한꺼번에 취소할 때도 같습니다.

```python
async def cancel_after_100(client):
    calls = 0

    def callback(record):
        nonlocal calls
        calls += 1
        time.sleep(0.001)

    task = asyncio.ensure_future(client.query("test", "demo").foreach(callback))
    while calls < 100:
        await asyncio.sleep(0.001)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    at_cancel = calls
    await asyncio.sleep(0.5)
    print(f"callbacks when CancelledError was raised: {at_cancel}, half a second later: {calls}")
```

```text
# 0.14.x
callbacks when CancelledError was raised: 100, half a second later: 468
# 0.15
callbacks when CancelledError was raised: 100, half a second later: 100
```

(여기서 `client`는 `AsyncClient`이고, set에는 record가 5,000개 있습니다.)

#### `async for`와 `query.stream()`

이제 `AsyncQuery`를 순회할 수 있습니다: `async for record in query`. `query.stream(policy)`도 같은 `AsyncRecordStream`을 반환하며, 이 객체는 async context manager이기도 하고 `close()`를 갖습니다. 첫 record를 요청하기 전에는 아무것도 보내지 않습니다. Consumer의 속도와 관계없이 client에서 대기하는 record는 query마다 최대 `record_queue_size`개(기본값 1024. 여기에 Python으로 넘겨주는 중인 묶음과, 자리가 나기를 기다리는 reader가 있는 node마다 record 하나가 더해집니다)이며, consumer가 `socket_timeout`보다 오래 멈춰도 됩니다. 읽기를 다시 시작하면 client가 나머지를 다시 가져오며 record를 중복해서 넘기지 않습니다. 여러 task가 같은 stream을 순회해도 되고, 각 record는 그중 한 task에만 전달됩니다. [Query 가이드](/docs/guides/query-scan#async-streaming)를 참고하세요.

Stream으로 코드를 옮길 때 알아 둘 점이 두 가지 있습니다.

- 다음 record를 기다리는 task를 취소하면 stream이 닫힙니다. 취소된 읽기가 이미 record를 가져갔을 수 있으므로, 그 뒤 같은 stream을 읽으면 순회가 끝나는 대신 `RuntimeError`가 발생합니다. `asyncio.wait_for(anext(stream), t)`는 시간이 다 되면 읽기를 취소합니다. 기다리는 시간을 제한하려면 loop 전체에 timeout을 거세요.
- Client를 닫아도 이미 실행 중인 stream은 멈추지 않습니다. Stream은 갖고 있는 connection으로 끝까지 읽고, 아직 한 번도 읽지 않은 stream은 첫 읽기에서 실패합니다. Stream을 client보다 먼저 닫으세요.

```python
async for record in client.query("test", "demo"):
    ...
```

```text
# 0.14.x
TypeError: 'async for' requires an object with __aiter__ method, got AsyncQuery
# 0.15
(순회합니다)
```

#### `foreach()`는 coroutine function을 거부합니다

`AsyncQuery.foreach()`는 worker thread에서 callback을 호출하므로 callback을 await할 수 없습니다. 0.14.x에서 `async def` callback은 record마다 아무도 await하지 않는 coroutine을 만들었고, coroutine은 `False`가 아니므로 scan을 멈추지도 못했습니다. 0.15는 `TypeError`를 발생시킵니다.

```python
async def handle(record):
    return False

await client.query("test", "demo").foreach(handle)
```

```text
# 0.14.x (scan 전체가 끝난 뒤 반환, record마다 warning 하나)
RuntimeWarning: coroutine 'main.<locals>.handle' was never awaited
# 0.15
TypeError: foreach() calls its callback from a worker thread and cannot await it; to await something for each record, use 'async for record in query'
```

**대응:** record마다 무언가를 await하려면 `async for record in query`를 사용하세요.

#### Scan을 일찍 끝내면 server에서도 멈춥니다

Sync client에도 적용됩니다. 0.14.x에서는 query를 중간에 그만 읽으면 client는 query를 버렸지만, server는 scan을 계속하면서 socket timeout(기본 30초)까지 connection을 붙잡았습니다. 0.15에서는 어떤 방법으로 빠져나와도 server의 query가 닫힙니다: `foreach()` callback이 `False`를 반환하거나 exception을 발생시킴, `async for`에서 `break`, `close()`, `async with` 블록을 벗어남, 취소, stream 오류, stream의 garbage collection.

Server의 job 목록(`query-show`)으로 측정했습니다. Record는 100,000개입니다.

| 멈춘 방법 | 0.14.x: scan이 계속 실행된 시간 | 0.15 |
|---|---|---|
| sync `foreach()` callback이 `False` 반환 | 30.3초 | 즉시 사라짐 |
| `async for`에서 `break` | (지원 안 함) | 0.1초 |

다른 경우가 하나 있습니다. 속도가 제한된 scan(`records_per_second`)은 server가 묶음을 멀리 떨어진 간격으로 보내며, 다음 묶음을 보낼 때가 될 때까지 server의 목록에 남아 있습니다. 초당 50 record에서 측정한 결과 45초였고, `socket_timeout`이 2000, 30000(기본값), 0일 때 모두 같았습니다. `socket_timeout`은 이 시간의 상한이 되지 않습니다.

### `apply()`도 `max_concurrent_operations`에 포함됩니다 {#apply-counts-against-max_concurrent_operations}

`max_concurrent_operations`를 설정하면 `batch_apply()`는 slot 하나를 차지했지만 단일 record `apply()`는 그렇지 않아서, UDF 호출은 한도를 넘어 실행되었습니다. 0.15에서는 `apply()`도 다른 record 명령처럼 slot을 기다리고, `operation_queue_timeout_ms`가 지나면 `BackpressureError`를 발생시킵니다.

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "max_concurrent_operations": 1,
    "operation_queue_timeout_ms": 100,
}
client = aerospike_py.AsyncClient(config)
await client.connect()
keys = [("test", "demo", "udf_0"), ("test", "demo", "udf_1")]
for key in keys:
    await client.put(key, {"v": 1})

# 각각 수백 ms 걸리는 UDF 호출 두 개, slot은 하나
outcomes = await asyncio.gather(
    *(client.apply(key, "slow_count", "run", [30_000_000]) for key in keys),
    return_exceptions=True,
)
for outcome in outcomes:
    print(type(outcome).__name__)
```

```text
# 0.14.x
int
int
# 0.15
int
BackpressureError
```

이 한도는 단일 record 명령(`apply()` 포함)과 batch 명령(`batch_apply()` 포함)을 셉니다. Query·scan stream, info, truncate, UDF 등록, index, admin 명령은 세지 않습니다. Stream이 slot을 차지하지 않는 것은 의도된 동작입니다. Stream은 consumer가 읽는 동안 계속 열려 있으므로, record마다 무언가를 조회하는 consumer는 자기 stream이 차지한 slot을 기다리게 됩니다.

**대응:** `max_concurrent_operations`를 설정했다면 UDF 호출까지 포함해 값을 정하고, `apply()` 주변에서 `BackpressureError`를 처리하세요.

### 새 node id로 재시작한 node {#node-restarts-with-a-new-node-id}

Node가 **같은 주소에서 새 node id로** 재시작하면(예: container 재시작), 오래 실행되는 client가 그 node로 다시 routing하기까지 cluster tend 주기 한 번(기본 약 1초)이 걸립니다. 그동안 명령이 `ClusterError`를 발생시킬 수 있습니다. 0.14.x에서는 몇 ms면 충분했습니다. Rust client 3.0은 이름이 더 이상 맞지 않는 node를 버리고 다음 tend에서 새 node를 알게 됩니다. 재시작 후에도 id가 같은 node는 이전처럼 바로 사용됩니다.

**대응:** node를 제자리에서 재시작한다면(rolling container 재시작, server를 재시작하는 test 등) node id를 고정하거나, 재시작 후 약 1초 동안 `ClusterError`를 retry하세요.

### 동시 batch 부하에서의 memory {#memory-under-concurrent-batch-load}

0.15에서는 동시 batch 부하가 걸린 client process가 memory를 더 사용합니다. 같은 workload를 두 버전에서 실행한 process memory(RSS)는 다음과 같습니다.

| Workload | 0.14.4 | 0.15 |
|---|---|---|
| 존재하는 record 720개 × bin 8개 `batch_read`, 동시 호출 8개, CPU를 쓰는 경쟁 thread 포함 | peak 66–70 MiB | peak 75–77 MiB |
| 같은 batch, 동시 호출 32개, batch 192,000개(약 3분) | 138 MiB에서 184 MiB까지 오른 뒤 마지막 53,000개 동안 평평함 | 201 MiB에서 257 MiB까지 오른 뒤 마지막 35,000개 동안 평평함 |
| 존재하는 key 50,000개짜리 `batch_read` 한 번 | key당 peak memory 2.2 KiB | key당 2.7 KiB (약 +20%) |
| 존재하지 않는 key 50,000개짜리 `batch_read` 한 번 | key당 2.0 KiB | key당 2.4 KiB (약 +20%) |

두 버전 모두 memory가 계단식으로 오르다가 오르는 간격이 길어지고 멈춥니다. 누수가 아니라 client가 보관하는 buffer memory입니다. 동시 호출 32개에서 차이는 73 MiB였고(같은 test의 이전 실행에서는 55–60 MiB), 0.15는 부하가 이어지는 동안 이 memory를 돌려주지 않습니다. 원인은 Rust client 3.0에 있습니다. Batch row 하나가 memory를 약 20% 더 차지하고, connection마다 64 KiB read buffer를 유지하며(이전 4 KiB), client가 큰 buffer를 명령마다 해제하지 않고 재사용하려고 크기가 제한된 pool에 보관합니다(크기 class마다 최대 4 MiB, 쓰지 않게 된 buffer는 약 1분 뒤에 해제).

**대응:** memory 한도를 0.14.x에 맞춰 빠듯하게 잡았다면 여유를 두세요. 추가 memory는 동시에 진행 중인 batch 호출 수에 따라 늘어납니다. 두 번의 측정에서 8개일 때 약 5–15 MiB, 32개일 때 약 55–75 MiB였습니다. `use_buffer_pool=False` 또는 `buffer_pool_tier_bytes` 설정을 조절하고 최대 RSS와 지연을 함께 측정할 수 있습니다.

처리량, 꼬리 지연, 최대 RSS는 서로 다르게 변할 수 있습니다. 실제 레코드 너비와 동시성으로 꼬리 지연과 최대 RSS를 측정한 뒤 worker 수를 결정하세요.

### Logging

aerospike-py는 예상하지 못한 오류를 만나면 "This error may be a bug in aerospike-py"라는 문구와 issue를 등록하는 명령을 error log로 남깁니다. 0.14.x는 평범한 실패에도 이 log를 남겼습니다: library가 거부한 인자(`TypeError`, `ValueError`), 사용자 `foreach` callback이 발생시킨 exception, 실패한 UDF, node 장애, client timeout. 0.15는 이런 경우 그 log 없이 호출자에게 exception을 전달합니다. `AerospikeError`가 아닌 그 밖의 오류는 여전히 log로 남깁니다.

```python
import logging

logging.basicConfig(level=logging.WARNING)
try:
    client.get(("test", "demo", None))  # None은 server가 저장할 수 있는 key가 아님
except ValueError as exc:
    print("raised:", exc)
```

```text
# 0.14.x
ERROR:aerospike_py:Unexpected internal error in aerospike-py (Client.get): ValueError: Invalid key: ...
This error may be a bug in aerospike-py. Please report it by running:
gh issue create ...
raised: Invalid key: Invalid argument: Data type is not supported as Key value.

# 0.15
raised: Invalid key: Error 4: Invalid argument: Data type is not supported as Key value.
```

### 그 밖의 변경

- NumPy의 `_namespace`·`_set`은 UTF-8 고정 너비 스칼라 바이트 필드여야 합니다. 잘못된 레이아웃이나 UTF-8은 배치 전송 전에 거부합니다. `V<N>` 키는 끝의 0바이트를 보존하며 `S<N>` 키는 패딩을 제거합니다. 예전 writer로 `V2` 키 `b"K\x00"`를 저장했다면 레코드는 `b"K"`의 digest에 있습니다. 동일 레코드로 유지하려면 새 writer가 다른 digest에 쓰기 전에 데이터를 이관하세요.
- 필터 조건, 명시적인 상대 TTL을 사용하거나 bin 삭제만 수행하는 쓰기의 결과가 불확실하면 바인딩의 재시도 대상에서 제외합니다. 행별 결과를 확인한 뒤 재전송 여부를 결정하세요.
- AsyncClient 한 개가 동시에 실행하는 쿼리는 기본 16개입니다. `max_concurrent_queries`로 조정할 수 있고 0이면 무제한입니다. 일반 CRUD는 별도 제한을 사용합니다.

- Client의 `timeout`과 `idle_timeout`은 30초 기본값을 유지합니다. Rust client 3.0은 자체 기본값을 낮췄지만, aerospike-py가 이전 값을 명시적으로 설정합니다.
- Map bin을 읽으면 key가 server가 돌려준 순서로 나오고, 읽을 때마다 같습니다(server 8.2에서는 key 순 정렬이며 정수가 문자열보다 앞). 0.14.x는 같은 map의 key를 읽을 때마다 다른 순서로 돌려줬습니다. dict끼리 비교하는 코드는 영향이 없고, 순회 순서에 기대던 코드는 원래도 믿을 수 없었습니다.
- `meta.ttl`은 공식 Python client처럼 초 단위로 계산합니다. `ttl=1000`으로 쓴 직후 읽은 record는 `1000`을 알립니다. 0.14.x는 거의 항상 `999`를 알렸습니다(측정에서 400번 중 398번, 0.15는 400번 중 398번이 `1000`). Client의 시계가 server보다 늦으면, 몇 ms 차이여도 설정한 값보다 1초 큰 값이 나올 수 있습니다. `meta.ttl <= ttl`을 그대로 단정하지 말고 1초의 여유를 두세요.

## 0.13.0 → 0.14.0 {#v0-14}

리스트 정렬에 숫자 플래그를 전달한다면 값을 확인하세요. 0.13.0에서는 알 수 없는 값을 기본 정렬로 처리했고, 0.14.0에서는 해당 연산을 실행할 때 `ValueError`가 발생합니다. 기본 정렬에는 `LIST_SORT_DEFAULT`(0), 중복 제거에는 `LIST_SORT_DROP_DUPLICATES`(2)를 사용하세요.

0.14.0부터 예외의 `result_code`로 서버 오류를 구분할 수 있습니다. 예를 들어 `remove()`로 없는 레코드를 삭제하면 `RecordNotFound.result_code`는 2입니다. [0.14.0 릴리스 노트](https://github.com/aerospike-ce-ecosystem/aerospike-py/releases/tag/v0.14.0)
