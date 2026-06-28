from tlddr.understand.edges import validate_edges
from tlddr.models import Edge, RelationType


def e(target, relation=RelationType.CORROBORATES):
    return Edge(target=target, relation=relation, rationale="r")


def test_drops_edge_to_unknown_target():
    valid, dropped = validate_edges([e("ghost")], known_node_ids={"a", "b"}, source_id="a")
    assert valid == []
    assert [d.target for d in dropped] == ["ghost"]


def test_keeps_edge_to_known_target():
    valid, dropped = validate_edges([e("b")], known_node_ids={"a", "b"}, source_id="a")
    assert [v.target for v in valid] == ["b"]
    assert dropped == []


def test_drops_self_link():
    valid, dropped = validate_edges([e("a")], known_node_ids={"a"}, source_id="a")
    assert valid == []
    assert [d.target for d in dropped] == ["a"]


def test_dedupes_same_target_and_relation():
    valid, _ = validate_edges([e("b"), e("b")], known_node_ids={"a", "b"}, source_id="a")
    assert len(valid) == 1
