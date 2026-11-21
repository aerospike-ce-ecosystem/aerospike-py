"""Unknown policy enum values are rejected before anything is sent.

The policy parsers in ``rust/src/policy/`` now raise ``InvalidArgError`` for an
``exists``, ``gen``, ``commit_level``, ``replica``, ``read_mode_ap`` or
``expected_duration`` value that no enum variant matches. They used to fall back
to the enum default without a word: ``exists=9`` turned a create-only write into
a plain update, and ``gen=9`` switched the generation check off.

The write tests prove that nothing reached the server: the record written first
keeps its bins and its generation after the rejected call. A silent fallback to
the default would have overwritten the bins and bumped the generation.

The valid constants are exercised as well, so a parser that rejected every value
would also fail here.

Only keys that the parser behind a call actually reads are tested:

- ``put``/``operate``/``remove``/... (``parse_write_policy``): ``exists``,
  ``gen``, ``commit_level``, ``read_mode_ap`` in ``policy``; ``exists`` and
  ``commit_level`` in ``meta``. In ``meta``, ``gen`` is an expected generation
  number, not a ``POLICY_GEN_*`` enum.
- ``batch_write`` / ``batch_write_numpy``: ``exists``, ``gen``,
  ``commit_level``, ``replica``, ``read_mode_ap``; per-record meta ``exists``
  and ``commit_level``.
- ``batch_operate``: ``replica`` and ``read_mode_ap`` only.
- ``batch_remove``: ``gen``, ``commit_level``, ``replica``, ``read_mode_ap``;
  per-record meta ``commit_level``.
- reads and ``batch_read``: ``replica`` and ``read_mode_ap``.
- queries: ``replica``, ``read_mode_ap`` and ``expected_duration``.
"""

import re

import numpy as np
import pytest

import aerospike_py
from tests.helpers import invoke

NS = "test"
SET = "policy_value_validation"

# Largest valid integer of each enum. The first rejected value sits right above
# it, so an off-by-one in a parser's range shows up as a failure.
_LAST_VALID = {
    "exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY,
    "gen": aerospike_py.POLICY_GEN_GT,
    "commit_level": aerospike_py.POLICY_COMMIT_LEVEL_MASTER,
    "replica": aerospike_py.POLICY_REPLICA_PREFER_RACK,
    "read_mode_ap": aerospike_py.POLICY_READ_MODE_AP_ALL,
    "expected_duration": aerospike_py.QUERY_DURATION_LONG_RELAX_AP,
}

SEED_BINS = {"n": 1, "s": "a"}
WRITE_OPS = [{"op": aerospike_py.OPERATOR_WRITE, "bin": "n", "val": 2}]

# Single-record write calls that go through ``parse_write_policy``:
# method name -> positional arguments after the key.
SINGLE_WRITES = {
    "put": ({"n": 2},),
    "operate": (WRITE_OPS,),
    "operate_ordered": (WRITE_OPS,),
    "remove": (),
    "touch": (),
    "increment": ("n", 1),
    "append": ("s", "x"),
    "prepend": ("s", "x"),
    "remove_bin": (["s"],),
}


def _past_range(name):
    return _LAST_VALID[name] + 1


def _bad_params(*names):
    """One case per name and bad value: just past the range, and negative."""
    return [pytest.param(name, bad, id=f"{name}={bad}") for name in names for bad in (_past_range(name), -1)]


def _rejects(name, bad):
    """Expect the parser's own rejection, not some later server error."""
    return pytest.raises(aerospike_py.InvalidArgError, match=re.escape(f"invalid {name} value: {bad} "))


async def _seed(client, cleanup, tag):
    """Write the seed record under a fresh key and return the key."""
    key = (NS, SET, tag)
    cleanup.append(key)
    await invoke(client, "put", key, dict(SEED_BINS))
    return key


async def _state(client, key):
    """``(bins, generation)`` of a stored record."""
    record = await invoke(client, "get", key)
    return record.bins, record.meta.gen


async def _result_codes(client, keys):
    handle = await invoke(client, "batch_read", keys)
    return [br.result for br in handle.batch_records]


# ── single-record writes ────────────────────────────────────────


class TestSingleRecordWriteRejectsUnknownValues:
    @pytest.mark.parametrize("method", list(SINGLE_WRITES))
    @pytest.mark.parametrize("name", ["exists", "gen", "commit_level", "read_mode_ap"])
    async def test_policy_value_past_range(self, any_client, any_cleanup, method, name):
        """Each write call rejects the first value past the range and sends nothing."""
        bad = _past_range(name)
        key = await _seed(any_client, any_cleanup, f"{method}-{name}")

        with _rejects(name, bad):
            await invoke(any_client, method, key, *SINGLE_WRITES[method], policy={name: bad})

        assert await _state(any_client, key) == (SEED_BINS, 1)

    @pytest.mark.parametrize(("name", "bad"), _bad_params("exists", "gen", "commit_level", "read_mode_ap"))
    async def test_put_policy_rejects_both_ends(self, any_client, any_cleanup, name, bad):
        """Negative values are rejected too, not only values above the range."""
        key = await _seed(any_client, any_cleanup, f"put-{name}-{bad}")

        with _rejects(name, bad):
            await invoke(any_client, "put", key, {"n": 2}, policy={name: bad})

        assert await _state(any_client, key) == (SEED_BINS, 1)

    @pytest.mark.parametrize("method", ["put", "operate", "remove", "touch", "increment"])
    @pytest.mark.parametrize(("name", "bad"), _bad_params("exists", "commit_level"))
    async def test_meta_value(self, any_client, any_cleanup, method, name, bad):
        """``meta`` carries ``exists`` and ``commit_level`` through the same enum parsers."""
        key = await _seed(any_client, any_cleanup, f"meta-{method}-{name}-{bad}")

        with _rejects(name, bad):
            await invoke(any_client, method, key, *SINGLE_WRITES[method], meta={name: bad})

        assert await _state(any_client, key) == (SEED_BINS, 1)

    async def test_create_only_typo_no_longer_overwrites(self, any_client, any_cleanup):
        """The motivating bug: ``exists=9`` used to become a plain update.

        The caller asked for some create-style write on a key that already
        exists. The old fallback overwrote the bins; now the call fails.
        """
        key = await _seed(any_client, any_cleanup, "exists-typo")

        with _rejects("exists", 9):
            await invoke(any_client, "put", key, {"n": 99, "s": "overwritten"}, policy={"exists": 9})

        assert await _state(any_client, key) == (SEED_BINS, 1)

    async def test_gen_typo_no_longer_disables_the_check(self, any_client, any_cleanup):
        """The motivating bug: ``gen=9`` used to become ``POLICY_GEN_IGNORE``.

        With a stale expected generation in ``meta``, the old fallback dropped
        the generation check and the write went through.
        """
        key = await _seed(any_client, any_cleanup, "gen-typo")

        with _rejects("gen", 9):
            await invoke(any_client, "put", key, {"n": 99}, meta={"gen": 50}, policy={"gen": 9})

        assert await _state(any_client, key) == (SEED_BINS, 1)


# What ``put(key, {"n": 2})`` does under each ``POLICY_EXISTS_*`` value: the
# bins stored afterwards, or the exception raised (the record is then left as
# it was).
EXISTS_ON_EXISTING = [
    pytest.param(aerospike_py.POLICY_EXISTS_IGNORE, {"n": 2, "s": "a"}, id="IGNORE"),
    pytest.param(aerospike_py.POLICY_EXISTS_UPDATE_ONLY, {"n": 2, "s": "a"}, id="UPDATE_ONLY"),
    pytest.param(aerospike_py.POLICY_EXISTS_REPLACE, {"n": 2}, id="REPLACE"),
    pytest.param(aerospike_py.POLICY_EXISTS_REPLACE_ONLY, {"n": 2}, id="REPLACE_ONLY"),
    pytest.param(aerospike_py.POLICY_EXISTS_CREATE_ONLY, aerospike_py.RecordExistsError, id="CREATE_ONLY"),
]
EXISTS_ON_MISSING = [
    pytest.param(aerospike_py.POLICY_EXISTS_IGNORE, {"n": 2}, id="IGNORE"),
    pytest.param(aerospike_py.POLICY_EXISTS_UPDATE_ONLY, aerospike_py.RecordNotFound, id="UPDATE_ONLY"),
    pytest.param(aerospike_py.POLICY_EXISTS_REPLACE, {"n": 2}, id="REPLACE"),
    pytest.param(aerospike_py.POLICY_EXISTS_REPLACE_ONLY, aerospike_py.RecordNotFound, id="REPLACE_ONLY"),
    pytest.param(aerospike_py.POLICY_EXISTS_CREATE_ONLY, {"n": 2}, id="CREATE_ONLY"),
]

# (gen policy, expected generation minus the stored one, whether the write succeeds)
GEN_CASES = [
    pytest.param(aerospike_py.POLICY_GEN_IGNORE, 5, True, id="IGNORE-stale"),
    pytest.param(aerospike_py.POLICY_GEN_EQ, 0, True, id="EQ-current"),
    pytest.param(aerospike_py.POLICY_GEN_EQ, 5, False, id="EQ-stale"),
    pytest.param(aerospike_py.POLICY_GEN_GT, 0, False, id="GT-current"),
    pytest.param(aerospike_py.POLICY_GEN_GT, 5, True, id="GT-ahead"),
]

READ_VALUES = [
    pytest.param("replica", aerospike_py.POLICY_REPLICA_MASTER, id="replica=MASTER"),
    pytest.param("replica", aerospike_py.POLICY_REPLICA_SEQUENCE, id="replica=SEQUENCE"),
    pytest.param("read_mode_ap", aerospike_py.POLICY_READ_MODE_AP_ONE, id="read_mode_ap=ONE"),
    pytest.param("read_mode_ap", aerospike_py.POLICY_READ_MODE_AP_ALL, id="read_mode_ap=ALL"),
]


class TestSingleRecordWriteAcceptsValidValues:
    @pytest.mark.parametrize("via", ["policy", "meta"])
    @pytest.mark.parametrize(("exists", "outcome"), EXISTS_ON_EXISTING)
    async def test_every_exists_constant_on_an_existing_record(self, any_client, any_cleanup, via, exists, outcome):
        """Each ``POLICY_EXISTS_*`` value keeps its own action, in ``policy`` and in ``meta``."""
        key = await _seed(any_client, any_cleanup, f"exists-{via}-{exists}-existing")
        call = invoke(any_client, "put", key, {"n": 2}, **{via: {"exists": exists}})

        if isinstance(outcome, dict):
            await call
            assert await _state(any_client, key) == (outcome, 2)
        else:
            with pytest.raises(outcome):
                await call
            assert await _state(any_client, key) == (SEED_BINS, 1)

    @pytest.mark.parametrize("via", ["policy", "meta"])
    @pytest.mark.parametrize(("exists", "outcome"), EXISTS_ON_MISSING)
    async def test_every_exists_constant_on_a_missing_record(self, any_client, any_cleanup, via, exists, outcome):
        key = (NS, SET, f"exists-{via}-{exists}-missing")
        any_cleanup.append(key)
        call = invoke(any_client, "put", key, {"n": 2}, **{via: {"exists": exists}})

        if isinstance(outcome, dict):
            await call
            assert await _state(any_client, key) == (outcome, 1)
        else:
            with pytest.raises(outcome):
                await call
            assert await _result_codes(any_client, [key]) == [2]

    @pytest.mark.parametrize(("gen_policy", "offset", "succeeds"), GEN_CASES)
    async def test_every_gen_constant_keeps_its_meaning(self, any_client, any_cleanup, gen_policy, offset, succeeds):
        """``policy["gen"]`` selects the check applied to ``meta["gen"]``."""
        key = await _seed(any_client, any_cleanup, f"gen-{gen_policy}-{offset}")
        call = invoke(any_client, "put", key, {"n": 2}, meta={"gen": 1 + offset}, policy={"gen": gen_policy})

        if succeeds:
            await call
            assert await _state(any_client, key) == ({"n": 2, "s": "a"}, 2)
        else:
            with pytest.raises(aerospike_py.RecordGenerationError):
                await call
            assert await _state(any_client, key) == (SEED_BINS, 1)

    async def test_meta_gen_is_a_generation_number_not_an_enum(self, any_client, any_cleanup):
        """``meta={"gen": 9}`` is an expected generation, so it is not range-checked.

        It must reach the server and fail the generation check there, rather
        than be rejected as an unknown ``POLICY_GEN_*`` value.
        """
        key = await _seed(any_client, any_cleanup, "meta-gen-number")

        with pytest.raises(aerospike_py.RecordGenerationError):
            await invoke(any_client, "put", key, {"n": 2}, meta={"gen": 9})

        assert await _state(any_client, key) == (SEED_BINS, 1)

    @pytest.mark.parametrize("via", ["policy", "meta"])
    @pytest.mark.parametrize(
        "level",
        [aerospike_py.POLICY_COMMIT_LEVEL_ALL, aerospike_py.POLICY_COMMIT_LEVEL_MASTER],
        ids=["ALL", "MASTER"],
    )
    async def test_commit_level_constants_are_accepted(self, any_client, any_cleanup, via, level):
        key = await _seed(any_client, any_cleanup, f"commit-{via}-{level}")

        await invoke(any_client, "put", key, {"n": 2}, **{via: {"commit_level": level}})

        assert await _state(any_client, key) == ({"n": 2, "s": "a"}, 2)

    @pytest.mark.parametrize(
        "mode",
        [aerospike_py.POLICY_READ_MODE_AP_ONE, aerospike_py.POLICY_READ_MODE_AP_ALL],
        ids=["ONE", "ALL"],
    )
    async def test_read_mode_ap_constants_are_accepted_on_operate(self, any_client, any_cleanup, mode):
        key = await _seed(any_client, any_cleanup, f"operate-read-mode-{mode}")
        ops = [*WRITE_OPS, {"op": aerospike_py.OPERATOR_READ, "bin": "s", "val": None}]

        record = await invoke(any_client, "operate", key, ops, policy={"read_mode_ap": mode})

        assert record.bins == {"s": "a"}
        assert await _state(any_client, key) == ({"n": 2, "s": "a"}, 2)


# ── batch writes ────────────────────────────────────────────────


class TestBatchWriteRejectsUnknownValues:
    @pytest.mark.parametrize(("name", "bad"), _bad_params("exists", "gen", "commit_level", "replica", "read_mode_ap"))
    async def test_batch_write_policy(self, any_client, any_cleanup, name, bad):
        """No row of the batch is sent: neither the update nor the new record."""
        key = await _seed(any_client, any_cleanup, f"bw-{name}-{bad}")
        new_key = (NS, SET, f"bw-{name}-{bad}-new")
        any_cleanup.append(new_key)

        with _rejects(name, bad):
            await invoke(any_client, "batch_write", [(new_key, {"n": 5}), (key, {"n": 2})], policy={name: bad})

        assert await _state(any_client, key) == (SEED_BINS, 1)
        assert await _result_codes(any_client, [new_key]) == [2]

    @pytest.mark.parametrize(("name", "bad"), _bad_params("exists", "commit_level"))
    async def test_batch_write_record_meta(self, any_client, any_cleanup, name, bad):
        """A bad per-record meta value fails the whole call, including rows before it."""
        key = await _seed(any_client, any_cleanup, f"bw-meta-{name}-{bad}")
        new_key = (NS, SET, f"bw-meta-{name}-{bad}-new")
        any_cleanup.append(new_key)
        records = [(new_key, {"n": 5}), (key, {"n": 2}, {name: bad})]

        with _rejects(name, bad):
            await invoke(any_client, "batch_write", records)

        assert await _state(any_client, key) == (SEED_BINS, 1)
        assert await _result_codes(any_client, [new_key]) == [2]

    @pytest.mark.parametrize(("name", "bad"), _bad_params("exists", "gen", "commit_level", "replica", "read_mode_ap"))
    async def test_batch_write_numpy_policy(self, any_client, any_cleanup, name, bad):
        # Integer user keys, so the keys checked below are exactly the ones the
        # array would have written.
        tag = 1000 * (list(_LAST_VALID).index(name) + 1) + bad
        key = await _seed(any_client, any_cleanup, tag)
        new_key = (NS, SET, tag + 500)
        any_cleanup.append(new_key)
        data = np.array([(new_key[2], 5), (key[2], 2)], dtype=[("_key", "i8"), ("n", "i8")])

        with _rejects(name, bad):
            await invoke(any_client, "batch_write_numpy", data, NS, SET, policy={name: bad})

        assert await _state(any_client, key) == (SEED_BINS, 1)
        assert await _result_codes(any_client, [new_key]) == [2]

    @pytest.mark.parametrize(("name", "bad"), _bad_params("replica", "read_mode_ap"))
    async def test_batch_operate_policy(self, any_client, any_cleanup, name, bad):
        key = await _seed(any_client, any_cleanup, f"bo-{name}-{bad}")

        with _rejects(name, bad):
            await invoke(any_client, "batch_operate", [key], WRITE_OPS, policy={name: bad})

        assert await _state(any_client, key) == (SEED_BINS, 1)

    @pytest.mark.parametrize(("name", "bad"), _bad_params("gen", "commit_level", "replica", "read_mode_ap"))
    async def test_batch_remove_policy(self, any_client, any_cleanup, name, bad):
        key = await _seed(any_client, any_cleanup, f"brm-{name}-{bad}")

        with _rejects(name, bad):
            await invoke(any_client, "batch_remove", [key], policy={name: bad})

        assert await _state(any_client, key) == (SEED_BINS, 1)

    @pytest.mark.parametrize(("name", "bad"), _bad_params("commit_level"))
    async def test_batch_remove_record_meta(self, any_client, any_cleanup, name, bad):
        """A bad meta value on the second key keeps the first key from being removed too."""
        first = await _seed(any_client, any_cleanup, f"brm-meta-{bad}-first")
        second = await _seed(any_client, any_cleanup, f"brm-meta-{bad}-second")

        with _rejects(name, bad):
            await invoke(any_client, "batch_remove", [first, (second, {name: bad})])

        assert await _state(any_client, first) == (SEED_BINS, 1)
        assert await _state(any_client, second) == (SEED_BINS, 1)


class TestBatchWriteAcceptsValidValues:
    async def test_batch_write_create_only_policy(self, any_client, any_cleanup):
        """``POLICY_EXISTS_CREATE_ONLY`` is honoured per row: 5 for the existing key, 0 for the new one."""
        key = await _seed(any_client, any_cleanup, "bw-create-only")
        new_key = (NS, SET, "bw-create-only-new")
        any_cleanup.append(new_key)

        result = await invoke(
            any_client,
            "batch_write",
            [(key, {"n": 2}), (new_key, {"n": 5})],
            policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
        )

        assert [br.result for br in result.batch_records] == [5, 0]
        assert await _state(any_client, key) == (SEED_BINS, 1)
        assert await _state(any_client, new_key) == ({"n": 5}, 1)

    async def test_batch_write_create_only_record_meta(self, any_client, any_cleanup):
        key = await _seed(any_client, any_cleanup, "bw-meta-create-only")
        new_key = (NS, SET, "bw-meta-create-only-new")
        any_cleanup.append(new_key)
        meta = {"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY}

        result = await invoke(any_client, "batch_write", [(key, {"n": 2}, meta), (new_key, {"n": 5}, meta)])

        assert [br.result for br in result.batch_records] == [5, 0]
        assert await _state(any_client, key) == (SEED_BINS, 1)

    async def test_batch_remove_gen_eq_policy(self, any_client, any_cleanup):
        """``POLICY_GEN_EQ`` on ``batch_remove`` is honoured: a stale generation keeps the record."""
        key = await _seed(any_client, any_cleanup, "brm-gen-eq")

        result = await invoke(any_client, "batch_remove", [key], policy={"gen": aerospike_py.POLICY_GEN_EQ})

        # No meta: the expected generation is 0, which never matches.
        assert [br.result for br in result.batch_records] == [3]
        assert await _state(any_client, key) == (SEED_BINS, 1)

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            pytest.param("replica", aerospike_py.POLICY_REPLICA_MASTER, id="replica=MASTER"),
            pytest.param("replica", aerospike_py.POLICY_REPLICA_SEQUENCE, id="replica=SEQUENCE"),
            pytest.param("read_mode_ap", aerospike_py.POLICY_READ_MODE_AP_ONE, id="read_mode_ap=ONE"),
            pytest.param("read_mode_ap", aerospike_py.POLICY_READ_MODE_AP_ALL, id="read_mode_ap=ALL"),
        ],
    )
    async def test_batch_operate_accepts_valid_policy_values(self, any_client, any_cleanup, name, value):
        key = await _seed(any_client, any_cleanup, f"bo-valid-{name}-{value}")

        result = await invoke(any_client, "batch_operate", [key], WRITE_OPS, policy={name: value})

        assert [br.result for br in result.batch_records] == [0]
        assert await _state(any_client, key) == ({"n": 2, "s": "a"}, 2)


# ── reads, batch reads and queries ──────────────────────────────


class TestReadsRejectUnknownValues:
    @pytest.mark.parametrize("method", ["get", "select", "exists", "batch_read"])
    @pytest.mark.parametrize(("name", "bad"), _bad_params("replica", "read_mode_ap"))
    async def test_read_policy(self, any_client, any_cleanup, method, name, bad):
        key = await _seed(any_client, any_cleanup, f"read-{method}-{name}-{bad}")
        args = {
            "get": (key,),
            "select": (key, ["n"]),
            "exists": (key,),
            "batch_read": ([key],),
        }[method]

        with _rejects(name, bad):
            await invoke(any_client, method, *args, policy={name: bad})

    @pytest.mark.parametrize("method", ["results", "foreach"])
    @pytest.mark.parametrize(("name", "bad"), _bad_params("replica", "read_mode_ap", "expected_duration"))
    async def test_query_policy(self, any_client, any_cleanup, method, name, bad):
        await _seed(any_client, any_cleanup, f"query-{method}-{name}-{bad}")
        seen = []
        args = () if method == "results" else (seen.append,)

        with _rejects(name, bad):
            await invoke(any_client.query(NS, SET), method, *args, policy={name: bad})

        assert seen == []


class TestReadsAcceptValidValues:
    @pytest.mark.parametrize(("name", "value"), READ_VALUES)
    async def test_get_and_batch_read(self, any_client, any_cleanup, name, value):
        key = await _seed(any_client, any_cleanup, f"read-valid-{name}-{value}")

        record = await invoke(any_client, "get", key, policy={name: value})
        handle = await invoke(any_client, "batch_read", [key], policy={name: value})

        assert record.bins == SEED_BINS
        assert handle.to_list() == [SEED_BINS]

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            *READ_VALUES,
            pytest.param("expected_duration", aerospike_py.QUERY_DURATION_LONG, id="expected_duration=LONG"),
            pytest.param("expected_duration", aerospike_py.QUERY_DURATION_SHORT, id="expected_duration=SHORT"),
            pytest.param(
                "expected_duration", aerospike_py.QUERY_DURATION_LONG_RELAX_AP, id="expected_duration=LONG_RELAX_AP"
            ),
        ],
    )
    async def test_query(self, any_client, any_cleanup, name, value):
        set_name = f"{SET}_query_{name}_{value}"
        key = (NS, set_name, "q")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, dict(SEED_BINS))

        records = await invoke(any_client.query(NS, set_name), "results", policy={name: value})

        assert [r.bins for r in records] == [SEED_BINS]

    async def test_prefer_rack_passes_the_parser(self, any_client, any_cleanup):
        """``POLICY_REPLICA_PREFER_RACK`` (2) is the last valid replica value.

        The test client configures no rack, so the core client may refuse the
        request afterwards. That refusal must not be the parser's "invalid
        replica value" rejection.
        """
        key = await _seed(any_client, any_cleanup, "prefer-rack")

        try:
            record = await invoke(any_client, "get", key, policy={"replica": aerospike_py.POLICY_REPLICA_PREFER_RACK})
        except aerospike_py.InvalidArgError as exc:
            assert "invalid replica value" not in str(exc)
        else:
            assert record.bins == SEED_BINS


class TestAFilterThatIsNotAnExpression:
    """A filter that is ignored lets through exactly what it was there to stop."""

    @pytest.mark.parametrize("bogus", ["v == 1", 1, ["eq"], {"op": "eq"}], ids=["str", "int", "list", "dict"])
    async def test_a_write_is_refused_and_the_record_stays_as_it_was(self, any_client, any_cleanup, bogus):
        key = (NS, SET, f"filter_not_expression_{type(bogus).__name__}")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})

        with pytest.raises(aerospike_py.InvalidArgError, match="filter_expression must be an expression"):
            await invoke(any_client, "put", key, {"v": 99}, policy={"filter_expression": bogus})

        record = await invoke(any_client, "get", key)
        assert (record.bins, record.meta.gen) == ({"v": 1}, 1)

    @pytest.mark.parametrize("method", ["get", "batch_read", "batch_remove"])
    async def test_reads_and_batches_refuse_it_too(self, any_client, any_cleanup, method):
        key = (NS, SET, f"filter_not_expression_{method}")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})
        argument = key if method == "get" else [key]

        with pytest.raises(aerospike_py.InvalidArgError, match="filter_expression must be an expression"):
            await invoke(any_client, method, argument, policy={"filter_expression": "v == 1"})

        assert (await invoke(any_client, "get", key)).bins == {"v": 1}

    async def test_none_means_no_filter(self, any_client, any_cleanup):
        key = (NS, SET, "filter_none")
        any_cleanup.append(key)

        await invoke(any_client, "put", key, {"v": 1}, policy={"filter_expression": None})

        assert (await invoke(any_client, "get", key)).bins == {"v": 1}


class TestIntegersThatDoNotFit:
    async def test_the_largest_max_retries_is_refused_instead_of_failing_unsent(self, any_client, any_cleanup):
        """The Rust client counts ``max_retries + 1`` attempts; for the largest value that is zero."""
        key = (NS, SET, "max_retries_wraps")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})

        for method, arguments in (("get", (key,)), ("put", (key, {"v": 2})), ("batch_read", ([key],))):
            with pytest.raises(aerospike_py.InvalidArgError, match="max_retries is too large"):
                await invoke(any_client, method, *arguments, policy={"max_retries": 2**64 - 1})

        assert (await invoke(any_client, "get", key)).bins == {"v": 1}

    async def test_the_largest_retry_reports_its_attempts(self, any_client, any_cleanup):
        key = (NS, SET, "retry_wraps")
        any_cleanup.append(key)

        result = await invoke(any_client, "batch_write", [(key, {"v": 1})], retry=2**32 - 1)

        assert (result.retry.attempts, result.retry.max_attempts) == (1, 2**32 - 1)

    @pytest.mark.parametrize(
        ("method", "arguments", "keywords"),
        [
            ("batch_write", ([((NS, SET, "does_not_fit"), {"v": 1})],), {"retry": -1}),
            ("put", ((NS, SET, "does_not_fit"), {"v": 1}), {"policy": {"total_timeout": -1}}),
            ("put", ((NS, SET, "does_not_fit"), {"v": 1}), {"policy": {"max_retries": -1}}),
            ("put", ((NS, SET, "does_not_fit"), {"v": 1}), {"meta": {"ttl": 2**70}}),
        ],
        ids=["retry", "total_timeout", "max_retries", "ttl"],
    )
    async def test_an_integer_out_of_range_is_the_callers_error_not_a_bug_report(
        self, any_client, any_cleanup, caplog, method, arguments, keywords
    ):
        any_cleanup.append((NS, SET, "does_not_fit"))

        with caplog.at_level("DEBUG"), pytest.raises((OverflowError, ValueError, aerospike_py.AerospikeError)):
            await invoke(any_client, method, *arguments, **keywords)

        assert [r.getMessage()[:100] for r in caplog.records if "may be a bug in aerospike-py" in r.getMessage()] == []

    async def test_a_queue_no_query_can_have_is_refused(self, client, async_client, caplog):
        """The record queue cannot have more than 2**61 - 1 slots. Asking for more was a panic."""
        too_large = {"record_queue_size": 2**61}
        refused = pytest.raises(aerospike_py.InvalidArgError, match="record_queue_size is too large")

        with caplog.at_level("DEBUG"):
            with refused:
                client.query(NS, SET).results(too_large)
            with refused:
                client.query(NS, SET).foreach(lambda _record: None, too_large)
            with refused:
                await async_client.query(NS, SET).results(too_large)
            with refused:
                await async_client.query(NS, SET).foreach(lambda _record: None, too_large)
            with refused:
                async_client.query(NS, SET).stream(too_large)

        assert [r.getMessage()[:100] for r in caplog.records if "may be a bug in aerospike-py" in r.getMessage()] == []

    async def test_the_largest_queue_there_can_be_is_accepted(self, any_client, any_cleanup):
        key = (NS, SET, "largest_queue")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"v": 1})

        found = any_client.query(NS, SET).results({"record_queue_size": 2**61 - 1})
        if hasattr(found, "__await__"):
            found = await found

        assert "largest_queue" in {record.key[2] for record in found if record.key is not None} or any(
            record.bins == {"v": 1} for record in found
        )


class TestARecordWithoutBins:
    """``batch_write`` cannot write an empty record, and says so before it sends anything.

    The Rust client refuses to build the request for a node whose share of the
    batch contains such a record, so the valid records that happened to live on
    the same node failed with it while those on other nodes were written: which
    records an argument error took down depended on the partition map.
    """

    @pytest.mark.parametrize("position", [0, 1, 2])
    async def test_it_is_refused_and_no_record_is_written(self, any_client, any_cleanup, position):
        keys = [(NS, SET, f"no_bins_{position}_{i}") for i in range(3)]
        any_cleanup.extend(keys)
        records = [(key, {"v": i}) for i, key in enumerate(keys)]
        records[position] = (keys[position], {})

        with pytest.raises(aerospike_py.InvalidArgError, match=f"record {position} has no bins"):
            await invoke(any_client, "batch_write", records)

        found = await invoke(any_client, "batch_read", keys)
        assert [row.result for row in found.batch_records] == [aerospike_py.AEROSPIKE_ERR_RECORD_NOT_FOUND] * 3

    async def test_a_single_empty_record_is_refused_the_same_way(self, any_client, any_cleanup):
        key = (NS, SET, "no_bins_alone")
        any_cleanup.append(key)

        with pytest.raises(aerospike_py.InvalidArgError, match="record 0 has no bins"):
            await invoke(any_client, "batch_write", [(key, {})])

    async def test_a_bin_set_to_none_is_a_write(self, any_client, any_cleanup):
        """Removing a bin is something to send; only no bins at all is nothing."""
        key = (NS, SET, "no_bins_but_a_removal")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"keep": 1, "drop": 2})

        result = await invoke(any_client, "batch_write", [(key, {"drop": None})])

        assert [row.result for row in result.batch_records] == [0]
        assert (await invoke(any_client, "get", key)).bins == {"keep": 1}

    async def test_an_array_without_bin_fields_is_refused(self, any_client, any_cleanup):
        data = np.zeros(3, np.dtype([("_key", "i8"), ("_note", "S4")]))
        data["_key"] = [9601, 9602, 9603]

        with pytest.raises(ValueError, match="dtype has no bin fields"):
            await invoke(any_client, "batch_write_numpy", data, NS, SET)

        found = await invoke(any_client, "batch_read", [(NS, SET, int(k)) for k in data["_key"]])
        assert [row.result for row in found.batch_records] == [aerospike_py.AEROSPIKE_ERR_RECORD_NOT_FOUND] * 3
