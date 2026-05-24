from tests.feasibility import conftest as feasibility_conftest


def test_feasibility_server_endpoint_uses_aerospike_env(monkeypatch):
    monkeypatch.setenv("AEROSPIKE_HOST", "aerospike-ci")
    monkeypatch.setenv("AEROSPIKE_PORT", "3000")

    assert feasibility_conftest._server_endpoint() == ("aerospike-ci", 3000)
