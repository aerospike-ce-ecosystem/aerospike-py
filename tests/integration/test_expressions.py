"""Integration tests for expression filters (requires Aerospike server)."""

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
        assert len(result.batch_records) == 6
        matched = [br for br in result.batch_records if br.result == 0]
        filtered = [br for br in result.batch_records if br.result != 0]
        # score >= 30: indices 3(30), 4(40), 5(50) => 3 matched
        assert len(matched) == 3
        assert len(filtered) == 3
        for br in matched:
            _, _, bins = br.record
            assert bins["score"] >= 30

    def test_batch_read_expression_all_filtered(self, client):
        """batch_read where expression filters all records."""
        expr = exp.gt(exp.int_bin("score"), exp.int_val(999))
        result = client.batch_read(self.keys, policy={"filter_expression": expr})
        for br in result.batch_records:
            assert br.result != 0


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
