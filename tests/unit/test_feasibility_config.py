from pathlib import Path

from tests.feasibility import conftest as feasibility_conftest


def test_server_available_uses_aerospike_env(monkeypatch):
    connected_to = []

    class FakeSocket:
        def settimeout(self, timeout):
            pass

        def connect(self, address):
            connected_to.append(address)

        def close(self):
            pass

    monkeypatch.setenv("AEROSPIKE_HOST", "aerospike-ci")
    monkeypatch.setenv("AEROSPIKE_PORT", "3000")
    monkeypatch.setattr(feasibility_conftest.socket, "socket", FakeSocket)

    assert feasibility_conftest._server_available()
    assert connected_to == [("aerospike-ci", 3000)]


def test_gunicorn_wsgi_app_uses_aerospike_env():
    test_file = Path(__file__).parents[1] / "feasibility" / "test_gunicorn.py"
    source = test_file.read_text()

    assert 'os.environ.get("AEROSPIKE_HOST", "127.0.0.1")' in source
    assert 'os.environ.get("AEROSPIKE_PORT", "18710")' in source
