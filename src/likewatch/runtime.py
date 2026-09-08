"""Bounded background acquisition/OCR and independent network delivery."""

import queue
import threading
import time
from PySide6.QtCore import QThread, Signal
from .capture import Capture
from .ocr import OcrSupervisor
from .rules import RuleState, describe, evaluate
from .diagnostics import logger
from .domain import Observation, Quality
from .messaging import deliver, poll_acknowledgements
from .snapshots import incident_snapshot, rule_variables


class MonitorWorker(QThread):
    result = Signal(object)
    captured = Signal(object)
    error = Signal(int, str)
    history = Signal(int, object)

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.jobs = queue.Queue(maxsize=1)
        self.revision = 0
        self.commit_guard = threading.Lock()
        self.stopping = threading.Event()
        self.states = {}
        self.frame_id = 0
        self.last_data = 0

    def submit(self, job):
        try:
            self.jobs.put_nowait(job)
            return True
        except queue.Full:
            return False

    def run(self):
        capture, ocr = Capture(), OcrSupervisor()
        try:
            self.store.prune()
            while not self.stopping.is_set():
                try:
                    revision, profile, action, payload = self.jobs.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    if revision != self.revision:
                        continue
                    if action == "snapshot":
                        try:
                            frame = capture.read(profile)
                        finally:
                            capture.close()
                        if revision == self.revision:
                            self.captured.emit((revision, frame, time.time()))
                    elif action == "ack":
                        self.store.acknowledge(payload)
                    elif action == "retry":
                        self.store.retry_uncertain(profile.id)
                    elif action == "test":
                        self.store.enqueue(
                            profile, "TEST", "LiKeWatch destination test"
                        )
                    elif action in ("capture", "ocr"):
                        if action == "ocr":
                            frame, timestamp = payload
                        else:
                            frame = capture.read(profile)
                            timestamp = time.time()
                        self.frame_id += 1
                        h, w = frame.shape[:2]
                        eligible = [
                            r
                            for r in profile.regions
                            if r.source_key == profile.source_key()
                            and r.source_size == [w, h]
                        ]
                        observations, previews = ocr.analyze(
                            frame, eligible, timestamp, self.frame_id
                        )
                        for region in profile.regions:
                            if region not in eligible:
                                observations[region.id] = Observation(
                                    region.id,
                                    "Verify region for this source / resolution",
                                    0,
                                    Quality.SOURCE_ERROR,
                                    None,
                                    timestamp,
                                    self.frame_id,
                                )
                        with self.commit_guard:
                            if revision != self.revision:
                                continue
                            if action == "ocr":
                                phases = {
                                    r.id: (
                                        "PREVIEW",
                                        evaluate(
                                            r.condition,
                                            observations,
                                            timestamp,
                                            profile.freshness,
                                        ).name,
                                    )
                                    for r in profile.rules
                                }
                                self.result.emit(
                                    (
                                        revision,
                                        frame,
                                        observations,
                                        previews,
                                        timestamp,
                                        phases,
                                    )
                                )
                                continue
                            active = self.store.active(profile.id)
                            for rule in profile.rules:
                                key = (profile.id, rule.id, revision)
                                state = self.states.setdefault(
                                    key, RuleState(incident_id=active.get(rule.id))
                                )
                                event = state.advance(
                                    rule, observations, time.time(), profile.freshness
                                )
                                if event:
                                    kind, incident = event
                                    ids = rule_variables(rule.condition)
                                    selected = [r for r in profile.regions if r.id in ids]
                                    values = "\n".join(
                                        f"{r.name}: {observations[r.id].value if observations[r.id].current(timestamp, profile.freshness) else 'unavailable'} {r.unit}"
                                        for r in selected
                                    )
                                    attachment = None
                                    if profile.attach_snapshot and profile.delivery_enabled and kind in profile.routes:
                                        try:
                                            attachment = incident_snapshot(frame, [r for r in selected if r in eligible])
                                        except Exception:
                                            logger.warning("Incident snapshot unavailable; sending text alert")
                                    self.store.enqueue(
                                        profile, kind,
                                        f"Rule: {rule.name} ({describe(rule.condition, {r.id: r for r in profile.regions})})\n{values}",
                                        incident, rule, now=timestamp, attachment=attachment,
                                    )
                            self.states = {
                                k: v for k, v in self.states.items() if k[2] == revision
                            }
                            if (
                                profile.data_interval
                                and time.time() - self.last_data
                                >= profile.data_interval
                            ):
                                values = "\n".join(
                                    f"{r.name}: {observations[r.id].value if observations[r.id].current(time.time(), profile.freshness) else 'unavailable'} {r.unit} ({observations[r.id].quality})"
                                    for r in profile.regions
                                )
                                self.store.enqueue(
                                    profile, "DATA", values, now=timestamp
                                )
                                self.last_data = time.time()
                            phases = {
                                r.id: (
                                    self.states[(profile.id, r.id, revision)].phase,
                                    self.states[
                                        (profile.id, r.id, revision)
                                    ].truth.name,
                                )
                                for r in profile.rules
                            }
                            self.result.emit(
                                (
                                    revision,
                                    frame,
                                    observations,
                                    previews,
                                    timestamp,
                                    phases,
                                )
                            )
                    self.history.emit(revision, self.store.history(profile.id))
                except Exception as error:
                    logger.exception("Monitor operation %s failed", action)
                    for state in self.states.values():
                        state.count = state.recovery_count = 0
                    # Network errors are handled elsewhere; never expose token-bearing URLs.
                    self.error.emit(
                        revision, f"{type(error).__name__}: {str(error)[:180]}"
                    )
        finally:
            capture.close()
            ocr.close()


class DeliveryWorker(QThread):
    changed = Signal()
    warning = Signal(str)

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.profile_id = None
        self.profile = None
        self.last_poll = 0
        self.poll_warning = 0
        self.last_notify = 0
        self.stopping = threading.Event()

    def run(self):
        while not self.stopping.wait(0.1):
            if self.profile_id:
                try:
                    deliver(self.store, self.profile_id)
                    profile = self.profile
                    if profile and profile.id == self.profile_id and self.store.has_ack_targets(profile.id) and time.monotonic() - self.last_poll >= profile.interval:
                        self.last_poll = time.monotonic()
                        try:
                            poll_acknowledgements(self.store, profile)
                        except Exception:
                            if time.monotonic() - self.poll_warning > 60:
                                self.warning.emit("Telegram reply polling unavailable; check connection, bot webhook, or another poller")
                                self.poll_warning = time.monotonic()
                    if time.monotonic() - self.last_notify >= 1:
                        self.last_notify = time.monotonic()
                        self.changed.emit()
                except Exception:
                    logger.exception("Delivery worker failed")
