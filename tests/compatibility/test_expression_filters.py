"""Expression filter compatibility tests.

Compares aerospike_py.exp filter behavior with the official aerospike
expression module. Tests that identical expressions produce identical
filtering results across both clients.

Key concern: aerospike_py uses "filter_expression" policy key (per exp.py),
while the official client uses "expressions". Both should work on their
respective clients.
"""

import pytest

import aerospike_py
from aerospike_py import exp

aerospike = pytest.importorskip("aerospike")
from aerospike_helpers import expressions as off_exp  # noqa: E402

NS = "test"
SET = "compat_expr"


@pytest.fixture(autouse=True)
def seed_expr_data(rust_client, official_client):
    """Seed test data for expression filter tests."""
    keys = []
    for i in range(10):
        key = (NS, SET, f"expr_{i}")
        rust_client.put(
            key,
            {
                "id": i,
                "age": 20 + i,
                "name": f"user_{i}",
                "active": i % 2 == 0,
                "score": float(i * 10),
            },
            policy={"key": aerospike_py.POLICY_KEY_SEND},
        )
        keys.append(key)
    yield
    for key in keys:
        try:
            rust_client.remove(key)
        except Exception:
            pass


class TestExpressionComparison:
    """Basic comparison expression filters: gt, lt, eq."""

    def test_gt_filter_on_get(self, rust_client, official_client, cleanup):
        """Filter with age > 25 on get()."""
        key = (NS, SET, "expr_8")  # age=28, should pass

        # Rust client with expression filter
        rust_expr = exp.gt(exp.int_bin("age"), exp.int_val(25))
        _, _, r_bins = rust_client.get(key, policy={"filter_expression": rust_expr})
        assert r_bins["age"] == 28

        # Official client with expression filter
        off_expr = off_exp.GT(off_exp.IntBin("age"), 25).compile()
        _, _, o_bins = official_client.get(key, policy={"expressions": off_expr})
        assert o_bins["age"] == 28

    def test_gt_filter_filters_out(self, rust_client, official_client):
        """Record that doesn't match should raise FilteredOut or similar."""
        key = (NS, SET, "expr_0")  # age=20, should NOT pass age > 25

        rust_expr = exp.gt(exp.int_bin("age"), exp.int_val(25))
        with pytest.raises(aerospike_py.FilteredOut):
            rust_client.get(key, policy={"filter_expression": rust_expr})

        off_expr = off_exp.GT(off_exp.IntBin("age"), 25).compile()
        with pytest.raises(aerospike.exception.FilteredOut):
            official_client.get(key, policy={"expressions": off_expr})

    def test_eq_filter(self, rust_client, official_client, cleanup):
        """Equality filter: id == 5."""
        key = (NS, SET, "expr_5")

        rust_expr = exp.eq(exp.int_bin("id"), exp.int_val(5))
        _, _, r_bins = rust_client.get(key, policy={"filter_expression": rust_expr})
        assert r_bins["id"] == 5

        off_expr = off_exp.Eq(off_exp.IntBin("id"), 5).compile()
        _, _, o_bins = official_client.get(key, policy={"expressions": off_expr})
        assert o_bins["id"] == 5

    def test_lt_filter(self, rust_client, official_client, cleanup):
        """Less than filter: age < 22."""
        key = (NS, SET, "expr_1")  # age=21

        rust_expr = exp.lt(exp.int_bin("age"), exp.int_val(22))
        _, _, r_bins = rust_client.get(key, policy={"filter_expression": rust_expr})
        assert r_bins["age"] == 21

        off_expr = off_exp.LT(off_exp.IntBin("age"), 22).compile()
        _, _, o_bins = official_client.get(key, policy={"expressions": off_expr})
        assert o_bins["age"] == 21


class TestExpressionLogical:
    """Logical combination expressions: and_, or_, not_."""

    def test_and_combination(self, rust_client, official_client, cleanup):
        """AND: age >= 24 AND id % 2 == 0 (even id)."""
        key = (NS, SET, "expr_4")  # age=24, id=4 (even)

        rust_expr = exp.and_(
            exp.ge(exp.int_bin("age"), exp.int_val(24)),
            exp.eq(
                exp.num_mod(exp.int_bin("id"), exp.int_val(2)),
                exp.int_val(0),
            ),
        )
        _, _, r_bins = rust_client.get(key, policy={"filter_expression": rust_expr})
        assert r_bins["age"] == 24
        assert r_bins["id"] == 4

        off_expr = off_exp.And(
            off_exp.GE(off_exp.IntBin("age"), 24),
            off_exp.Eq(
                off_exp.Mod(off_exp.IntBin("id"), 2),
                0,
            ),
        ).compile()
        _, _, o_bins = official_client.get(key, policy={"expressions": off_expr})
        assert o_bins["age"] == 24

    def test_and_filters_out(self, rust_client, cleanup):
        """AND: age >= 24 AND id is even - should filter out expr_5 (odd id).

        Note: bool_bin + bool_val is not used because aerospike-core lacks a
        dedicated bool_bin() and its ExpOp is pub(crate), so bool_bin falls
        back to int_bin which causes a type mismatch with bool_val on the server.
        """
        key = (NS, SET, "expr_5")  # age=25, id=5 (odd)

        rust_expr = exp.and_(
            exp.ge(exp.int_bin("age"), exp.int_val(24)),
            exp.eq(
                exp.num_mod(exp.int_bin("id"), exp.int_val(2)),
                exp.int_val(0),
            ),
        )
        with pytest.raises(aerospike_py.FilteredOut):
            rust_client.get(key, policy={"filter_expression": rust_expr})

    def test_or_combination(self, rust_client, cleanup):
        """OR: id == 0 OR id == 9."""
        key = (NS, SET, "expr_0")

        rust_expr = exp.or_(
            exp.eq(exp.int_bin("id"), exp.int_val(0)),
            exp.eq(exp.int_bin("id"), exp.int_val(9)),
        )
        _, _, r_bins = rust_client.get(key, policy={"filter_expression": rust_expr})
        assert r_bins["id"] == 0

    def test_not_filter(self, rust_client, cleanup):
        """NOT: NOT (age > 25) - should allow age=20."""
        key = (NS, SET, "expr_0")  # age=20

        rust_expr = exp.not_(exp.gt(exp.int_bin("age"), exp.int_val(25)))
        _, _, r_bins = rust_client.get(key, policy={"filter_expression": rust_expr})
        assert r_bins["age"] == 20


class TestExpressionOnGet:
    """Expression applied to get() operations."""

    def test_expression_policy_key_name(self, rust_client, cleanup):
        """Verify that 'filter_expression' policy key works (from exp.py docstring)."""
        key = (NS, SET, "expr_3")

        rust_expr = exp.ge(exp.int_bin("age"), exp.int_val(20))
        _, _, bins = rust_client.get(key, policy={"filter_expression": rust_expr})
        assert bins is not None

    def test_expression_on_select(self, rust_client, cleanup):
        """Expression filter with select() - only return specific bins."""
        key = (NS, SET, "expr_5")  # age=25

        rust_expr = exp.eq(exp.int_bin("id"), exp.int_val(5))
        _, _, bins = rust_client.select(key, ["name", "age"], policy={"filter_expression": rust_expr})
        assert bins["name"] == "user_5"
        assert bins["age"] == 25
        assert "id" not in bins or "score" not in bins


class TestExpressionMetadata:
    """Expression filters using record metadata."""

    def test_key_exists_filter(self, rust_client, cleanup):
        """Filter records where key is stored."""
        key = (NS, SET, "expr_3")  # stored with POLICY_KEY_SEND

        rust_expr = exp.key_exists()
        _, _, bins = rust_client.get(key, policy={"filter_expression": rust_expr})
        assert bins["id"] == 3


class TestExpressionNumeric:
    """Numeric expression operations."""

    def test_num_mod_filter(self, rust_client, cleanup):
        """Filter: id % 3 == 0."""
        key = (NS, SET, "expr_6")  # id=6, 6%3=0

        rust_expr = exp.eq(
            exp.num_mod(exp.int_bin("id"), exp.int_val(3)),
            exp.int_val(0),
        )
        _, _, bins = rust_client.get(key, policy={"filter_expression": rust_expr})
        assert bins["id"] == 6

    def test_num_add_filter(self, rust_client, cleanup):
        """Filter: age + 10 > 35."""
        key = (NS, SET, "expr_7")  # age=27, 27+10=37>35

        rust_expr = exp.gt(
            exp.num_add(exp.int_bin("age"), exp.int_val(10)),
            exp.int_val(35),
        )
        _, _, bins = rust_client.get(key, policy={"filter_expression": rust_expr})
        assert bins["age"] == 27
