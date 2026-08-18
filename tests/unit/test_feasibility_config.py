from pathlib import Path

from tests import server as server_policy


def test_server_reachable_uses_aerospike_env(monkeypatch):
    """The reachability probe the feasibility suite gates on honours the env."""
    connected_to = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    def fake_create_connection(address, timeout=None):
        connected_to.append(address)
        return FakeConnection()

    monkeypatch.setenv("AEROSPIKE_HOST", "aerospike-ci")
    monkeypatch.setenv("AEROSPIKE_PORT", "3000")
    monkeypatch.setattr(server_policy.socket, "create_connection", fake_create_connection)

    assert server_policy.server_reachable()
    assert connected_to == [("aerospike-ci", 3000)]


def test_gunicorn_wsgi_app_uses_aerospike_env():
    test_file = Path(__file__).parents[1] / "feasibility" / "test_gunicorn.py"
    source = test_file.read_text()

    assert 'os.environ.get("AEROSPIKE_HOST", "127.0.0.1")' in source
    assert 'os.environ.get("AEROSPIKE_PORT", "18710")' in source
