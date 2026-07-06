import json
from pathlib import Path
from tlddr.runstate import STAGES, corpus_fingerprint, init_state, load_state, mark_stage


def test_fingerprint_is_stable_and_size_sensitive(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("world!!")
    fp1 = corpus_fingerprint(tmp_path)
    fp2 = corpus_fingerprint(tmp_path)
    assert fp1 == fp2 and fp1.startswith("sha256:")
    (tmp_path / "b.txt").write_text("world!! changed length")
    assert corpus_fingerprint(tmp_path) != fp1


def test_init_state_writes_all_stages_pending(tmp_path):
    sp = tmp_path / "state_lock.json"
    st = init_state(sp, {"preset": "quick"}, "sha256:abc")
    assert sp.exists()
    assert st["config"] == {"preset": "quick"}
    assert st["corpus_fingerprint"] == "sha256:abc"
    assert set(st["stages"]) == set(STAGES)
    assert all(st["stages"][s]["status"] == "pending" for s in STAGES)
    assert all(st["stages"][s]["rounds"] == 0 for s in STAGES)


def test_load_state_absent_is_none(tmp_path):
    assert load_state(tmp_path / "nope.json") is None


def test_mark_stage_sets_done_and_increments_rounds(tmp_path):
    sp = tmp_path / "state_lock.json"
    init_state(sp, {}, "sha256:x")
    mark_stage(sp, "draft", now="2026-07-06T00:00:00Z")
    st = mark_stage(sp, "draft", now="2026-07-06T01:00:00Z")
    assert st["stages"]["draft"]["status"] == "done"
    assert st["stages"]["draft"]["rounds"] == 2
    assert st["stages"]["draft"]["updated"] == "2026-07-06T01:00:00Z"
    assert st["stages"]["extract"]["status"] == "pending"


def test_mark_stage_creates_file_if_missing(tmp_path):
    sp = tmp_path / "state_lock.json"
    st = mark_stage(sp, "extract", now="2026-07-06T00:00:00Z")
    assert sp.exists() and st["stages"]["extract"]["rounds"] == 1
