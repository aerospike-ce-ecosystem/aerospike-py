from __future__ import annotations


def test_is_connected(client):
    resp = client.get("/cluster/connected")

    assert resp.status_code == 200
    assert resp.json() == {"connected": True}


def test_get_node_names(client):
    resp = client.get("/cluster/nodes")

    assert resp.status_code == 200
    nodes = resp.json()["nodes"]
    assert isinstance(nodes, list)
    assert len(nodes) >= 1
