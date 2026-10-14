"""Real filesystem/process tests for repository-owned compare-and-swap state."""
import json
import multiprocessing
import os

import pytest

from artoo.manifest import dumps, loads
from artoo.state import MAX_BODY, StateConflict, StateError, StateStore


@pytest.fixture
def store(tmp_path):
    return StateStore.for_artifact(tmp_path, tmp_path / "site", ["feedback"])


def test_opt_in_and_manifest_roundtrip(tmp_path):
    m = loads('[artifact]\nslug="test"\ntitle="Test"\n[state]\ncollections=["feedback"]')
    assert loads(dumps(m)).state_collections == ["feedback"]
    assert not m.validate()
    for site in (tmp_path, tmp_path / "state", tmp_path / "state/site"):
        with pytest.raises(StateError):
            StateStore.for_artifact(tmp_path, site, ["feedback"])
    with pytest.raises(StateError):
        StateStore(tmp_path / "state").list("feedback")


def test_legacy_read_revision_does_not_rewrite(store):
    path = store.root / 'feedback' / 'old.json'
    path.parent.mkdir(parents=True)
    raw = b'{"name":"old","updated":"yesterday","document":{"note":"keep"}}'
    path.write_bytes(raw)
    read = store.read('feedback', 'old')
    assert read['document'] == {'note': 'keep'}
    assert path.read_bytes() == raw
    with pytest.raises(StateConflict):
        store.write('feedback', 'old', {}, expected_revision=None)
    saved = store.write('feedback', 'old', {'note': 'new'}, expected_revision=read['revision'])
    assert saved['revision'] != read['revision']
    assert saved['git_committed'] is False


@pytest.mark.parametrize('name', ['..', '../bad', '/tmp/x', 'x/y', 'a\n', ''])
def test_invalid_names(store, name):
    with pytest.raises(StateError):
        store.write('feedback', name, {}, expected_revision=None)


@pytest.mark.parametrize('component', ['root', 'collection', 'file', 'lock'])
def test_symlinks_never_followed(store, tmp_path, component):
    outside = tmp_path / 'outside'
    outside.mkdir()
    victim = outside / 'v.json'
    victim.write_text('untouched')
    if component == 'root':
        store.root.symlink_to(outside, target_is_directory=True)
    else:
        store.root.mkdir()
        coll = store.root / 'feedback'
        if component == 'collection':
            coll.symlink_to(outside, target_is_directory=True)
        else:
            coll.mkdir()
            (coll / ('v.json' if component == 'file' else '.lock')).symlink_to(victim)
    with pytest.raises(StateError):
        store.write('feedback', 'v', {}, expected_revision=None)
    assert victim.read_text() == 'untouched'


def test_hardlinks_and_nonregular_files_rejected(store, tmp_path):
    coll = store.root / 'feedback'
    coll.mkdir(parents=True)
    victim = tmp_path / 'victim'
    victim.write_text('{}')
    os.link(victim, coll / 'v.json')
    with pytest.raises(StateError):
        store.read('feedback', 'v')
    os.mkfifo(coll / 'fifo.json')
    with pytest.raises(StateError):
        store.read('feedback', 'fifo')


def _compete(root, revision, start, queue):
    store = StateStore(root, collections=['feedback'])
    start.wait(10)
    try:
        store.write('feedback', 'shared', os.getpid(), expected_revision=revision)
        queue.put('saved')
    except StateConflict:
        queue.put('conflict')


def test_two_processes_cannot_overwrite_each_other(store):
    original = store.write('feedback', 'shared', 0, expected_revision=None)
    ctx = multiprocessing.get_context('spawn')
    start, queue = ctx.Event(), ctx.Queue()
    workers = [ctx.Process(target=_compete, args=(store.root, original['revision'], start, queue))
               for _ in range(2)]
    for worker in workers:
        worker.start()
    start.set()
    assert sorted(queue.get(timeout=20) for _ in workers) == ['conflict', 'saved']
    for worker in workers:
        worker.join(10)
        assert worker.exitcode == 0


def test_failed_replace_preserves_original_and_removes_temp(store, monkeypatch):
    original = store.write('feedback', 'v', {'value': 1}, expected_revision=None)
    def fail(*args, **kwargs):
        raise OSError('interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', fail)
        with pytest.raises(StateError):
            store.write('feedback', 'v', {'value': 2}, expected_revision=original['revision'])
    assert store.read('feedback', 'v') == original
    assert not list((store.root / 'feedback').glob('.pending-*'))
    store.write('feedback', 'v', {'value': 3}, expected_revision=original['revision'])


def test_lost_ack_can_be_reconciled_by_read(store, monkeypatch):
    original = store.write('feedback', 'v', 1, expected_revision=None)
    fsync = os.fsync
    calls = 0
    def fail_directory(fd):
        nonlocal calls
        calls += 1
        import stat
        if calls > 2 and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError('lost acknowledgement')
        return fsync(fd)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'fsync', fail_directory)
        with pytest.raises(StateError):
            store.write('feedback', 'v', 2, expected_revision=original['revision'])
    assert store.read('feedback', 'v')['document'] == 2
    with pytest.raises(StateConflict):
        store.write('feedback', 'v', 1, expected_revision=original['revision'])


def test_corrupt_and_oversized_data_preserved(store):
    for document in (float('nan'), {'x': float('inf')}, 'x' * MAX_BODY):
        with pytest.raises(StateError):
            store.write('feedback', 'v', document, expected_revision=None)
    coll = store.root / 'feedback'
    coll.mkdir(parents=True, exist_ok=True)
    path = coll / 'v.json'
    path.write_text('broken')
    with pytest.raises(StateError):
        store.write('feedback', 'v', {}, expected_revision=None)
    assert path.read_text() == 'broken'
    path.write_text(json.dumps({'name': 'v', 'updated': '', 'document': {}}))
    with pytest.raises(StateError):
        store.delete('feedback', 'v', expected_revision='bad')


def test_first_save_flushes_new_directory_entries(store, monkeypatch):
    import stat
    events = []
    real_fsync = os.fsync
    real_replace = os.replace
    def sync(fd):
        events.append('dir' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
        return real_fsync(fd)
    def replace(*args, **kwargs):
        events.append('replace')
        return real_replace(*args, **kwargs)
    monkeypatch.setattr(os, 'fsync', sync)
    monkeypatch.setattr(os, 'replace', replace)
    store.write('feedback', 'v', {}, expected_revision=None)
    assert events == ['dir', 'dir', 'file', 'replace', 'dir']


@pytest.mark.parametrize('raw', [
    '{"document":{}}',
    '{"name":"v","updated":"today","document":{},"document":1}',
])
def test_malformed_envelope_is_preserved(store, raw):
    path = store.root / 'feedback' / 'v.json'
    path.parent.mkdir(parents=True)
    path.write_text(raw)
    with pytest.raises(StateError):
        store.list('feedback')
    assert path.read_text() == raw


def test_precreated_state_is_the_only_writable_directory(store):
    artifact = store.root.parent
    store.root.mkdir()
    source = artifact / 'source.txt'
    source.write_text('read-only authoring source')
    source.chmod(0o444)
    artifact.chmod(0o555)
    try:
        saved = store.write('feedback', 'v', {'note': 'saved'}, expected_revision=None)
        assert store.read('feedback', 'v')['revision'] == saved['revision']
        assert source.read_text() == 'read-only authoring source'
    finally:
        artifact.chmod(0o755)
        source.chmod(0o644)


def test_readonly_artifacts_do_not_need_posix_locking(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'fcntl', None)
    assert not loads('[artifact]\nslug="test"\ntitle="Test"').validate()
    StateStore.for_artifact(tmp_path, tmp_path, [])
    with pytest.raises(StateError, match='POSIX'):
        StateStore.for_artifact(tmp_path, tmp_path / 'site', ['feedback'])


def _crash_before_replace(root, revision):
    def crash(*args, **kwargs):
        os._exit(17)
    os.replace = crash
    StateStore(root, collections=['feedback']).write('feedback', 'v', 'new',
                                                    expected_revision=revision)


def test_killed_writer_leaves_original_and_next_save_recovers(store):
    saved = store.write('feedback', 'v', 'original', expected_revision=None)
    worker = multiprocessing.get_context('spawn').Process(
        target=_crash_before_replace, args=(store.root, saved['revision']))
    worker.start()
    worker.join(15)
    assert worker.exitcode == 17
    assert store.read('feedback', 'v') == saved
    assert len(store.list('feedback')) == 1
    assert list((store.root / 'feedback').glob('.pending-*'))
    store.write('feedback', 'v', 'recovered', expected_revision=saved['revision'])
    assert store.read('feedback', 'v')['document'] == 'recovered'
