"""Async integration tests for UDF / batch_apply (requires Aerospike server)."""

from __future__ import annotations

import os

import pytest

UDF_FILE = os.path.join(os.path.dirname(__file__), "..", "test_udf.lua")


@pytest.fixture
async def async_udf_client(async_client):
    """Register the test UDF module on the async client for the test."""
    await async_client.udf_put(UDF_FILE)
    yield async_client
    try:
        await async_client.udf_remove("test_udf")
    except Exception:
        pass


class TestAsyncApply:
    async def test_apply_echo(self, async_udf_client):
        key = ("test", "demo", "async_udf_echo")
        await async_udf_client.put(key, {"a": 1})
        try:
            result = await async_udf_client.apply(key, "test_udf", "echo", [42])
            assert result == 42
        finally:
            await async_udf_client.remove(key)

    async def test_apply_add(self, async_udf_client):
        key = ("test", "demo", "async_udf_add")
        await async_udf_client.put(key, {"a": 1})
        try:
            result = await async_udf_client.apply(key, "test_udf", "add", [3, 4])
            assert result == 7
        finally:
            await async_udf_client.remove(key)


class TestAsyncBatchApply:
    async def test_batch_apply_basic(self, async_udf_client):
        keys = [("test", "demo", f"async_bapply_basic_{i}") for i in range(4)]
        for k in keys:
            await async_udf_client.put(k, {"x": 1})
        try:
            result = await async_udf_client.batch_apply(keys, "test_udf", "add", [10, 20])
            assert len(result.batch_records) == 4
            for br in result.batch_records:
                assert br.result == 0
        finally:
            for k in keys:
                await async_udf_client.remove(k)

    async def test_batch_apply_set_bin(self, async_udf_client):
        keys = [("test", "demo", f"async_bapply_set_{i}") for i in range(3)]
        for k in keys:
            await async_udf_client.put(k, {"x": 0})
        try:
            await async_udf_client.batch_apply(keys, "test_udf", "set_bin", ["x", 77])
            for k in keys:
                _, _, bins = await async_udf_client.get(k)
                assert bins["x"] == 77
        finally:
            for k in keys:
                await async_udf_client.remove(k)

    async def test_batch_apply_per_record_args_override(self, async_udf_client):
        k1 = ("test", "demo", "async_bapply_meta1")
        k2 = ("test", "demo", "async_bapply_meta2")
        for k in (k1, k2):
            await async_udf_client.put(k, {"x": 0, "y": 0})
        try:
            await async_udf_client.batch_apply(
                [
                    k1,
                    (k2, {"args": ["y", 9]}),
                ],
                "test_udf",
                "set_bin",
                args=["x", 5],
            )
            _, _, b1 = await async_udf_client.get(k1)
            _, _, b2 = await async_udf_client.get(k2)
            assert b1["x"] == 5
            assert b2["y"] == 9
            assert b2["x"] == 0
        finally:
            await async_udf_client.remove(k1)
            await async_udf_client.remove(k2)

    async def test_batch_apply_per_record_function_override(self, async_udf_client):
        k1 = ("test", "demo", "async_bapply_func1")
        k2 = ("test", "demo", "async_bapply_func2")
        for k in (k1, k2):
            await async_udf_client.put(k, {"x": 0})
        try:
            result = await async_udf_client.batch_apply(
                [
                    k1,  # default add
                    (k2, {"function": "echo", "args": ["hi"]}),
                ],
                "test_udf",
                "add",
                args=[1, 2],
            )
            assert len(result.batch_records) == 2
            for br in result.batch_records:
                assert br.result == 0
        finally:
            await async_udf_client.remove(k1)
            await async_udf_client.remove(k2)
