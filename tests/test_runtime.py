import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import threading
import time
import pytest
from PySide6.QtWidgets import QApplication
from likewatch.capture import demo_frame
from likewatch.domain import parse_observation
from likewatch.profiles import demo_profile
from likewatch.storage import Store
from likewatch.runtime import MonitorWorker


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, predicate, seconds=4):
    deadline = time.time() + seconds
    while not predicate() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


class FakeOcr:
    def analyze(self, frame, regions, timestamp, frame_id):
        return (
            {
                r.id: parse_observation(
                    r, "90" if i == 0 else "10", 99, timestamp, frame_id
                )
                for i, r in enumerate(regions)
            },
            {},
        )

    def close(self):
        pass


def test_same_frame_pipeline_and_source_change(app, tmp_path, monkeypatch):
    monkeypatch.setattr("likewatch.runtime.OcrSupervisor", FakeOcr)
    monkeypatch.setattr("likewatch.runtime.Capture.read", lambda *_: demo_frame())
    store = Store(tmp_path / "db")
    worker = MonitorWorker(store)
    p = demo_profile()
    results = []
    worker.result.connect(results.append)
    worker.start()
    try:
        for i in range(3):
            assert worker.submit((0, p, "capture", None))
            wait_for(app, lambda: len(results) == i + 1)
        assert len(store.active(p.id)) == 1
        p.source = "screen"
        assert worker.submit((0, p, "capture", None))
        wait_for(app, lambda: len(results) == 4)
        assert all(o.value is None for o in results[-1][2].values())
        assert len(store.active(p.id)) == 1
    finally:
        worker.stopping.set()
        assert worker.wait(5000)


def test_revision_discards_inflight_alert(app, tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    class Slow(FakeOcr):
        def analyze(self, *args):
            entered.set()
            release.wait(3)
            return super().analyze(*args)

    monkeypatch.setattr("likewatch.runtime.OcrSupervisor", Slow)
    monkeypatch.setattr("likewatch.runtime.Capture.read", lambda *_: demo_frame())
    store = Store(tmp_path / "db")
    worker = MonitorWorker(store)
    p = demo_profile()
    p.rules[0].confirm = 1
    results = []
    worker.result.connect(results.append)
    worker.start()
    try:
        worker.submit((0, p, "capture", None))
        assert entered.wait(2)
        with worker.commit_guard:
            worker.revision = 1
        release.set()
        worker.stopping.set()
        assert worker.wait(5000)
        app.processEvents()
        assert not results and not store.active(p.id) and not store.history(p.id)
    finally:
        release.set()
        worker.stopping.set()
        worker.wait(5000)


def test_condition_editor_accepts_imported_leaf(app):
    from likewatch.ui import ConditionEditor

    profile = demo_profile()
    leaf = profile.rules[0].condition["children"][0]
    editor = ConditionEditor(profile.regions, leaf)
    assert editor.value() == {"group": "ALL", "children": [leaf]}
    editor.deleteLater()


@pytest.mark.parametrize('attach,use_preview', [(False,False),(True,False),(True,True)])
def test_destination_incident_snapshot_and_history(app, tmp_path, monkeypatch, attach, use_preview):
    monkeypatch.setattr('likewatch.runtime.OcrSupervisor', FakeOcr)
    reads=[]
    monkeypatch.setattr('likewatch.runtime.Capture.read', lambda *_: reads.append(True) or demo_frame())
    store=Store(tmp_path/'db')
    p=demo_profile();p.delivery_enabled=True;p.chat_id='123'
    p.attach_snapshot=attach;p.local_alarm=True
    worker=MonitorWorker(store);history=[]
    worker.history.connect(lambda *args: history.append(args))
    worker.start()
    try:
        assert worker.submit((0,p,'test',demo_frame() if use_preview else None))
        wait_for(app,lambda:bool(history))
        row=store.claim(p.id)
        assert bool(row['attachment']) == attach
        assert bool(reads) == (attach and not use_preview)
        assert row['incident'] in store.pending_alarms(p.id)
        assert not store.active(p.id)
        assert 'Reply to this message with ACK' in row['body']
        store.delivered(row['seq'],'accepted',message_id=42)
        assert store.ack_reply(p.id,'123',None,42)
        assert not store.pending_alarms(p.id)
    finally:
        worker.stopping.set();assert worker.wait(5000)


def test_snapshot_test_failure_does_not_silently_send_text(app,tmp_path,monkeypatch):
    monkeypatch.setattr('likewatch.runtime.OcrSupervisor',FakeOcr)
    def fail(*_):
        raise ValueError('Capture unavailable')
    monkeypatch.setattr('likewatch.runtime.Capture.read',fail)
    store=Store(tmp_path/'db');p=demo_profile();p.attach_snapshot=True
    worker=MonitorWorker(store);errors=[];worker.error.connect(lambda *args:errors.append(args));worker.start()
    try:
        worker.submit((0,p,'test',None));wait_for(app,lambda:bool(errors))
        assert not store.history(p.id)
        assert 'Capture unavailable' in errors[0][1]
    finally:
        worker.stopping.set();assert worker.wait(5000)
