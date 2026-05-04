"""Integration tests for expression filters (requires Aerospike server)."""

import uuid

import pytest

import aerospike_py
from aerospike_py import exp


class TestExpressionGet:
    """Expression filters applied to get/put operations."""

    @pytest.fixture(autouse=True)
    def setup_records(self, client, cleanup):
        """Seed records for expression tests."""
        self.keys = []
        for i in range(5):
            key = ("test", "expr_test", f"expr_{i}")
            cleanup.append(key)
            client.put(key, {"age": 20 + i * 5, "name": f"user_{i}", "active": i % 2 == 0})
            self.keys.append(key)

    def test_eq_filter_match(self, client):
        """Expression eq filter should return the matching record."""
        key = self.keys[0]  # age=20
        expr = exp.eq(exp.int_bin("age"), exp.int_val(20))
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["age"] == 20

    def test_eq_filter_no_match(self, client):
        """Expression eq filter should raise FilteredOut when not matching."""
        key = self.keys[0]  # age=20
        expr = exp.eq(exp.int_bin("age"), exp.int_val(999))
        with pytest.raises(aerospike_py.FilteredOut):
            client.get(key, policy={"filter_expression": expr})

    def test_gt_filter(self, client):
        """Expression gt filter: age > 30."""
        key = self.keys[3]  # age=35
        expr = exp.gt(exp.int_bin("age"), exp.int_val(30))
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["age"] == 35

    def test_gt_filter_no_match(self, client):
        """Expression gt filter should raise FilteredOut for age <= 30."""
        key = self.keys[0]  # age=20
        expr = exp.gt(exp.int_bin("age"), exp.int_val(30))
        with pytest.raises(aerospike_py.FilteredOut):
            client.get(key, policy={"filter_expression": expr})

    def test_lt_filter(self, client):
        """Expression lt filter: age < 25."""
        key = self.keys[0]  # age=20
        expr = exp.lt(exp.int_bin("age"), exp.int_val(25))
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["age"] == 20

    def test_ge_filter(self, client):
        """Expression ge filter: age >= 25."""
        key = self.keys[1]  # age=25
        expr = exp.ge(exp.int_bin("age"), exp.int_val(25))
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["age"] == 25

    def test_le_filter(self, client):
        """Expression le filter: age <= 20."""
        key = self.keys[0]  # age=20
        expr = exp.le(exp.int_bin("age"), exp.int_val(20))
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["age"] == 20

    def test_ne_filter(self, client):
        """Expression ne filter: age != 20."""
        key = self.keys[1]  # age=25
        expr = exp.ne(exp.int_bin("age"), exp.int_val(20))
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["age"] == 25

    def test_and_filter(self, client):
        """Expression and_ filter: age >= 20 AND age < 30."""
        key = self.keys[1]  # age=25
        expr = exp.and_(
            exp.ge(exp.int_bin("age"), exp.int_val(20)),
            exp.lt(exp.int_bin("age"), exp.int_val(30)),
        )
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["age"] == 25

    def test_and_filter_no_match(self, client):
        """Expression and_ filter should raise FilteredOut when one condition fails."""
        key = self.keys[3]  # age=35
        expr = exp.and_(
            exp.ge(exp.int_bin("age"), exp.int_val(20)),
            exp.lt(exp.int_bin("age"), exp.int_val(30)),
        )
        with pytest.raises(aerospike_py.FilteredOut):
            client.get(key, policy={"filter_expression": expr})

    def test_or_filter(self, client):
        """Expression or_ filter: age == 20 OR age == 35."""
        key = self.keys[3]  # age=35
        expr = exp.or_(
            exp.eq(exp.int_bin("age"), exp.int_val(20)),
            exp.eq(exp.int_bin("age"), exp.int_val(35)),
        )
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["age"] == 35

    def test_or_filter_no_match(self, client):
        """Expression or_ filter should raise FilteredOut when no condition matches."""
        key = self.keys[1]  # age=25
        expr = exp.or_(
            exp.eq(exp.int_bin("age"), exp.int_val(20)),
            exp.eq(exp.int_bin("age"), exp.int_val(35)),
        )
        with pytest.raises(aerospike_py.FilteredOut):
            client.get(key, policy={"filter_expression": expr})

    def test_not_filter(self, client):
        """Expression not_ filter: NOT (age == 20)."""
        key = self.keys[1]  # age=25
        expr = exp.not_(exp.eq(exp.int_bin("age"), exp.int_val(20)))
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["age"] == 25

    def test_not_filter_no_match(self, client):
        """Expression not_ filter should raise FilteredOut on negated match."""
        key = self.keys[0]  # age=20
        expr = exp.not_(exp.eq(exp.int_bin("age"), exp.int_val(20)))
        with pytest.raises(aerospike_py.FilteredOut):
            client.get(key, policy={"filter_expression": expr})

    def test_string_eq_filter(self, client):
        """Expression filter on string bin."""
        key = self.keys[0]  # name="user_0"
        expr = exp.eq(exp.string_bin("name"), exp.string_val("user_0"))
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["name"] == "user_0"

    def test_string_eq_filter_no_match(self, client):
        """Expression string filter should raise FilteredOut on mismatch."""
        key = self.keys[0]  # name="user_0"
        expr = exp.eq(exp.string_bin("name"), exp.string_val("nonexistent"))
        with pytest.raises(aerospike_py.FilteredOut):
            client.get(key, policy={"filter_expression": expr})


class TestExpressionBatch:
    """Expression filters applied to batch operations."""

    @pytest.fixture(autouse=True)
    def setup_records(self, client, cleanup):
        """Seed records for batch expression tests."""
        self.keys = []
        for i in range(6):
            key = ("test", "expr_batch", f"bexpr_{i}")
            cleanup.append(key)
            client.put(key, {"score": i * 10, "group": "A" if i < 3 else "B"})
            self.keys.append(key)

    def test_batch_read_with_expression(self, client):
        """batch_read with filter_expression should filter at server side."""
        expr = exp.ge(exp.int_bin("score"), exp.int_val(30))
        result = client.batch_read(self.keys, policy={"filter_expression": expr})
        # score >= 30: indices 3(30), 4(40), 5(50) => 3 matched
        # Filtered records are excluded from the dict
        assert len(result) == 3
        for user_key, bins in result.items():
            assert bins["score"] >= 30

    def test_batch_read_expression_all_filtered(self, client):
        """batch_read where expression filters all records."""
        expr = exp.gt(exp.int_bin("score"), exp.int_val(999))
        result = client.batch_read(self.keys, policy={"filter_expression": expr})
        assert len(result) == 0


class TestExpressionMetadata:
    """Expression filters using record metadata."""

    def test_key_exists_filter(self, client, cleanup):
        """Filter by key_exists (record stored with POLICY_KEY_SEND)."""
        key = ("test", "expr_meta", "key_stored")
        cleanup.append(key)
        client.put(key, {"val": 1}, policy={"key": aerospike_py.POLICY_KEY_SEND})

        expr = exp.key_exists()
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["val"] == 1

    def test_key_exists_filter_no_key(self, client, cleanup):
        """key_exists should raise FilteredOut when key is not stored."""
        key = ("test", "expr_meta", "key_not_stored")
        cleanup.append(key)
        client.put(key, {"val": 1})  # default: key not stored

        expr = exp.key_exists()
        with pytest.raises(aerospike_py.FilteredOut):
            client.get(key, policy={"filter_expression": expr})

    def test_ttl_expression(self, client, cleanup):
        """Filter records whose TTL is above a threshold."""
        key = ("test", "expr_meta", "ttl_check")
        cleanup.append(key)
        client.put(key, {"val": 1}, meta={"ttl": 3600})

        # TTL should be > 0 (record has an expiration)
        expr = exp.gt(exp.ttl(), exp.int_val(0))
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["val"] == 1

    def test_bin_exists_filter(self, client, cleanup):
        """Filter by bin existence."""
        key = ("test", "expr_meta", "bin_exists_check")
        cleanup.append(key)
        client.put(key, {"present_bin": 42})

        expr = exp.bin_exists("present_bin")
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["present_bin"] == 42

    def test_bin_exists_filter_missing(self, client, cleanup):
        """bin_exists should raise FilteredOut when bin doesn't exist."""
        key = ("test", "expr_meta", "bin_missing_check")
        cleanup.append(key)
        client.put(key, {"other_bin": 1})

        expr = exp.bin_exists("missing_bin")
        with pytest.raises(aerospike_py.FilteredOut):
            client.get(key, policy={"filter_expression": expr})

    def test_complex_metadata_expression(self, client, cleanup):
        """Combine metadata and bin expression: key_exists AND age > 18."""
        key = ("test", "expr_meta", "complex")
        cleanup.append(key)
        client.put(
            key,
            {"age": 25},
            policy={"key": aerospike_py.POLICY_KEY_SEND},
        )

        expr = exp.and_(
            exp.key_exists(),
            exp.gt(exp.int_bin("age"), exp.int_val(18)),
        )
        _, _, bins = client.get(key, policy={"filter_expression": expr})
        assert bins["age"] == 25


class TestPkRegexFilterScan:
    """PK regex filter scan via exp.regex_compare(..., exp.key(EXP_TYPE_STRING)).

    Equivalent to Java client's
    ``Exp.regexCompare(pattern, RegexFlag.NONE, Exp.key(Exp.Type.STRING))``.
    Performs a full set scan with server-side filtering on the user key — does
    not use a primary index. Records must be written with POLICY_KEY_SEND.
    """

    @pytest.fixture(autouse=True)
    def _isolated_set(self):
        # Unique set per test invocation so stragglers from a previously
        # interrupted run cannot contaminate empty-result assertions.
        self.set_name = f"expr_pk_regex_{uuid.uuid4().hex[:12]}"

    def _seed(self, client, cleanup, user_keys, *, send_key):
        policy = {"key": aerospike_py.POLICY_KEY_SEND} if send_key else None
        for uk in user_keys:
            key = ("test", self.set_name, uk)
            cleanup.append(key)
            client.put(key, {"v": uk}, policy=policy)

    def test_pk_regex_filter_scan(self, client, cleanup):
        """^aaa.* matches only records whose user key starts with 'aaa'."""
        self._seed(client, cleanup, ["aaa001", "aaa002", "bbb001"], send_key=True)

        expr = exp.regex_compare(
            "^aaa.*",
            aerospike_py.REGEX_NONE,
            exp.key(exp.EXP_TYPE_STRING),
        )
        results = client.query("test", self.set_name).results(policy={"filter_expression": expr})

        matched = sorted(r.key.user_key for r in results if r.key is not None)
        assert matched == ["aaa001", "aaa002"]

    def test_pk_regex_filter_scan_no_send_key(self, client, cleanup):
        """Records without POLICY_KEY_SEND have no stored user key — no match.

        The empty result confirms that records in the set were *evaluated* by
        the filter and rejected (because they lack a stored user key), not
        that the scan failed. Compare with test_pk_regex_filter_scan_no_match,
        where records are stored with sendKey but the pattern excludes them.
        """
        self._seed(client, cleanup, ["aaa001", "aaa002"], send_key=False)

        expr = exp.regex_compare(
            "^aaa.*",
            aerospike_py.REGEX_NONE,
            exp.key(exp.EXP_TYPE_STRING),
        )
        results = client.query("test", self.set_name).results(policy={"filter_expression": expr})

        assert results == []

    def test_pk_regex_filter_scan_no_match(self, client, cleanup):
        """Pattern that matches nothing returns an empty list (filter ran)."""
        self._seed(client, cleanup, ["aaa001", "bbb001"], send_key=True)

        expr = exp.regex_compare(
            "^zzz.*",
            aerospike_py.REGEX_NONE,
            exp.key(exp.EXP_TYPE_STRING),
        )
        results = client.query("test", self.set_name).results(policy={"filter_expression": expr})

        assert results == []

    def test_pk_regex_filter_scan_icase(self, client, cleanup):
        """REGEX_ICASE matches user keys regardless of case."""
        self._seed(client, cleanup, ["AAA001", "aaa002", "bbb001"], send_key=True)

        expr = exp.regex_compare(
            "^aaa.*",
            aerospike_py.REGEX_ICASE,
            exp.key(exp.EXP_TYPE_STRING),
        )
        results = client.query("test", self.set_name).results(policy={"filter_expression": expr})

        matched = sorted(r.key.user_key for r in results if r.key is not None)
        assert matched == ["AAA001", "aaa002"]

    def test_pk_regex_filter_scan_integer_key_excluded(self, client, cleanup):
        """Integer user keys do not satisfy exp.key(EXP_TYPE_STRING).

        Documents the contract: when records in the same set have heterogeneous
        user-key types, `exp.key(EXP_TYPE_STRING)` only exposes the string
        ones. Integer-keyed records are filtered out (the expression evaluates
        to unknown for them) rather than raising — query continues over the
        rest of the set.
        """
        # Mix string and integer user keys, both written with sendKey.
        for key in [
            ("test", self.set_name, "aaa001"),
            ("test", self.set_name, "aaa002"),
            ("test", self.set_name, 12345),
            ("test", self.set_name, 67890),
        ]:
            cleanup.append(key)
            client.put(key, {"v": 1}, policy={"key": aerospike_py.POLICY_KEY_SEND})

        expr = exp.regex_compare(
            "^aaa.*",
            aerospike_py.REGEX_NONE,
            exp.key(exp.EXP_TYPE_STRING),
        )
        results = client.query("test", self.set_name).results(policy={"filter_expression": expr})

        matched = sorted(r.key.user_key for r in results if r.key is not None)
        assert matched == ["aaa001", "aaa002"]

    def test_pk_regex_filter_scan_bitwise_flag_combo(self, client, cleanup):
        """REGEX_ICASE | REGEX_EXTENDED both apply on a POSIX-extended pattern.

        Locks the bitfield contract: if any constant is changed to a
        non-orthogonal value the combined behaviour breaks immediately.
        ``[A-Za-z]{3}001`` requires REGEX_EXTENDED (counted repetition is a
        POSIX-extended construct); REGEX_ICASE adds case-insensitive matching.
        """
        # Sanity-check the bitfield itself.
        assert aerospike_py.REGEX_ICASE | aerospike_py.REGEX_EXTENDED == 3

        self._seed(
            client,
            cleanup,
            ["AAA001", "aaa002", "BB1001", "x002"],
            send_key=True,
        )

        expr = exp.regex_compare(
            "^[A-Z]{3}001$",
            aerospike_py.REGEX_ICASE | aerospike_py.REGEX_EXTENDED,
            exp.key(exp.EXP_TYPE_STRING),
        )
        results = client.query("test", self.set_name).results(policy={"filter_expression": expr})

        matched = sorted(r.key.user_key for r in results if r.key is not None)
        # Only "AAA001" and "aaa001"-style 3-letter+001 keys match. From the
        # seed, "AAA001" is the lone match (aaa002 fails the literal "001",
        # BB1001 fails the {3} letter run, x002 fails everything).
        assert matched == ["AAA001"]
