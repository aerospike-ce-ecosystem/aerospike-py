"""Integration tests for Admin operations (requires Aerospike server with security enabled)."""

import pytest

import aerospike_py


@pytest.fixture(scope="module")
def client():
    config = {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}
    try:
        c = aerospike_py.client(config).connect()
    except Exception:
        pytest.skip("Aerospike server not available")
    yield c
    c.close()


def skip_if_no_security(func):
    """Decorator to skip tests if security is not enabled on the server."""

    def wrapper(client, *args, **kwargs):
        try:
            return func(client, *args, **kwargs)
        except aerospike_py.AerospikeError as e:
            if "security" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Security not enabled on this server")
            raise

    return wrapper


class TestAdminUser:
    def test_create_and_drop_user(self, client):
        """Test creating and dropping a user."""
        try:
            client.admin_create_user("test_user_1", "password123", ["read-write"])
        except aerospike_py.AerospikeError as e:
            if "security" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Security not enabled on this server")
            raise

        try:
            user_info = client.admin_query_user_info("test_user_1")
            assert user_info["user"] == "test_user_1"
            assert "read-write" in user_info["roles"]
        finally:
            client.admin_drop_user("test_user_1")

    def test_grant_revoke_roles(self, client):
        """Test granting and revoking roles."""
        try:
            client.admin_create_user("test_user_2", "password123", ["read"])
        except aerospike_py.AerospikeError as e:
            if "security" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Security not enabled on this server")
            raise

        try:
            client.admin_grant_roles("test_user_2", ["read-write"])
            user_info = client.admin_query_user_info("test_user_2")
            assert "read-write" in user_info["roles"]

            client.admin_revoke_roles("test_user_2", ["read"])
            user_info = client.admin_query_user_info("test_user_2")
            assert "read" not in user_info["roles"]
        finally:
            client.admin_drop_user("test_user_2")

    def test_query_users(self, client):
        """Test querying all users."""
        try:
            users = client.admin_query_users_info()
            assert isinstance(users, list)
            # At least the admin user should exist
            assert len(users) >= 1
        except aerospike_py.AerospikeError as e:
            if "security" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Security not enabled on this server")
            raise

    def test_change_password(self, client):
        """Test changing a user's password."""
        try:
            client.admin_create_user("test_user_pw", "old_pass", ["read"])
        except aerospike_py.AerospikeError as e:
            if "security" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Security not enabled on this server")
            raise

        try:
            client.admin_change_password("test_user_pw", "new_pass")
        finally:
            client.admin_drop_user("test_user_pw")


class TestAdminRole:
    def test_create_and_drop_role(self, client):
        """Test creating and dropping a custom role."""
        try:
            client.admin_create_role(
                "test_role_1",
                [{"code": aerospike_py.PRIV_READ, "ns": "test", "set": "demo"}],
            )
        except aerospike_py.AerospikeError as e:
            if "security" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Security not enabled on this server")
            raise

        try:
            role_info = client.admin_query_role("test_role_1")
            assert role_info["name"] == "test_role_1"
            assert len(role_info["privileges"]) == 1
            assert role_info["privileges"][0]["code"] == aerospike_py.PRIV_READ
        finally:
            client.admin_drop_role("test_role_1")

    def test_grant_revoke_privileges(self, client):
        """Test granting and revoking privileges."""
        try:
            client.admin_create_role(
                "test_role_2",
                [{"code": aerospike_py.PRIV_READ}],
            )
        except aerospike_py.AerospikeError as e:
            if "security" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Security not enabled on this server")
            raise

        try:
            client.admin_grant_privileges(
                "test_role_2",
                [{"code": aerospike_py.PRIV_WRITE}],
            )
            role_info = client.admin_query_role("test_role_2")
            codes = [p["code"] for p in role_info["privileges"]]
            assert aerospike_py.PRIV_WRITE in codes

            client.admin_revoke_privileges(
                "test_role_2",
                [{"code": aerospike_py.PRIV_READ}],
            )
            role_info = client.admin_query_role("test_role_2")
            codes = [p["code"] for p in role_info["privileges"]]
            assert aerospike_py.PRIV_READ not in codes
        finally:
            client.admin_drop_role("test_role_2")

    def test_query_roles(self, client):
        """Test querying all roles."""
        try:
            roles = client.admin_query_roles()
            assert isinstance(roles, list)
            # Built-in roles should exist
            assert len(roles) >= 1
        except aerospike_py.AerospikeError as e:
            if "security" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Security not enabled on this server")
            raise
