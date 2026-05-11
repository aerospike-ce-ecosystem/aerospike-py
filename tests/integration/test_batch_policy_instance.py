"""Integration tests for the BatchPolicyInstance pyclass.

Verifies that a pre-parsed policy is accepted by batch_read on both
Client and AsyncClient, and produces the same results as the
equivalent dict-shaped policy.
"""

import aerospike_py
import pytest

NS = "test"
SET = "bpi"


class TestBatchPolicyInstance:
    def test_construct_with_no_kwargs(self):
        p = aerospike_py.BatchPolicyInstance()
        assert isinstance(p, aerospike_py.BatchPolicyInstance)

    def test_construct_with_typed_kwargs(self):
        p = aerospike_py.BatchPolicyInstance(
            socket_timeout=2000,
            total_timeout=5000,
            max_retries=3,
            concurrency=1,
            allow_inline=True,
        )
        assert isinstance(p, aerospike_py.BatchPolicyInstance)

    def test_unknown_kwarg_raises(self):
        with pytest.raises(TypeError):
            aerospike_py.BatchPolicyInstance(definitely_not_a_field=1)  # type: ignore[call-arg]

    def test_positional_args_rejected(self):
        """Constructor is keyword-only; passing positional args raises."""
        with pytest.raises(TypeError):
            aerospike_py.BatchPolicyInstance(2000)  # type: ignore[misc]


class TestBatchReadAcceptsInstance:
    def test_sync_client_accepts_instance(self, client, cleanup):
        keys = [(NS, SET, f"s_{i}") for i in range(3)]
        for i, k in enumerate(keys):
            cleanup.append(k)
            client.put(k, {"i": i})

        policy = aerospike_py.BatchPolicyInstance(socket_timeout=2000, max_retries=2)
        result = client.batch_read(keys, policy=policy)
        assert result == {f"s_{i}": {"i": i} for i in range(3)}

    async def test_async_client_accepts_instance(self, async_client, async_cleanup):
        keys = [(NS, SET, f"a_{i}") for i in range(3)]
        for i, k in enumerate(keys):
            async_cleanup.append(k)
            await async_client.put(k, {"i": i})

        policy = aerospike_py.BatchPolicyInstance(
            socket_timeout=2000, total_timeout=5000, max_retries=2
        )
        result = await async_client.batch_read(keys, policy=policy)
        assert result == {f"a_{i}": {"i": i} for i in range(3)}

    async def test_instance_and_dict_produce_equivalent_results(
        self, async_client, async_cleanup
    ):
        """A pyclass instance with field X = V must behave identically to
        ``{X: V}`` dict — verifies the parser parity."""
        keys = [(NS, SET, f"eq_{i}") for i in range(3)]
        for i, k in enumerate(keys):
            async_cleanup.append(k)
            await async_client.put(k, {"i": i})

        instance = aerospike_py.BatchPolicyInstance(
            socket_timeout=2000, total_timeout=5000, max_retries=2
        )
        dict_policy = {
            "socket_timeout": 2000,
            "total_timeout": 5000,
            "max_retries": 2,
        }
        from_instance = await async_client.batch_read(keys, policy=instance)
        from_dict = await async_client.batch_read(keys, policy=dict_policy)
        assert from_instance == from_dict

    def test_invalid_policy_arg_type_raises(self, client):
        """Anything that is not a dict, ``BatchPolicyInstance``, or None
        should fail at the type-check boundary."""
        with pytest.raises(TypeError):
            client.batch_read([(NS, SET, "k")], policy="not a policy")  # type: ignore[arg-type]
