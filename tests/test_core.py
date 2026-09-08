from decimal import Decimal
import pytest
import numpy as np
from likewatch.domain import Region, Rule, Quality, Observation, parse_observation
from likewatch.rules import Truth, evaluate, RuleState, validate_tree
from likewatch.imaging import validate_corners, rectify
from likewatch.profiles import save, load, demo_profile
from likewatch.storage import Store


@pytest.fixture
def region():
    return Region("A", [[0, 0], [1, 0], [1, 1], [0, 1]], id="a")


@pytest.mark.parametrize(
    "raw,value", [("0", "0"), ("-0.25", "-0.25"), ("+3.10", "3.10"), ("1e-3", "0.001")]
)
def test_precision(region, raw, value):
    obs = parse_observation(region, raw, 95, 10, 1)
    assert obs.value == Decimal(value) and obs.quality == Quality.VALID


@pytest.mark.parametrize(
    "raw", ["O.5", "1 kg", "1,2", "NaN", "Infinity", "1 2", "１.２", "1e999999"]
)
def test_bad_numbers_never_become_values(region, raw):
    obs = parse_observation(region, raw, 95, 10, 1)
    assert obs.value is None and obs.quality == Quality.PARSE_ERROR


def test_quality(region):
    assert parse_observation(region, "", 100, 0, 1).quality == Quality.EMPTY
    assert parse_observation(region, "1", 20, 0, 1).quality == Quality.LOW_CONFIDENCE
    region.minimum = "2"
    assert parse_observation(region, "1", 95, 0, 1).quality == Quality.OUT_OF_RANGE


def leaf(name="a", op=">", value="80"):
    return {"variable": name, "op": op, "value": value}


@pytest.mark.parametrize(
    "group,first,expected",
    [
        ("ALL", 90, Truth.UNKNOWN),
        ("ALL", 70, Truth.FALSE),
        ("ANY", 90, Truth.TRUE),
        ("ANY", 70, Truth.UNKNOWN),
    ],
)
def test_three_valued(region, group, first, expected):
    node = {"group": group, "children": [leaf(), leaf("missing")]}
    obs = {"a": parse_observation(region, str(first), 95, 10, 1)}
    assert evaluate(node, obs, 10, 3) == expected
    assert evaluate(leaf(), obs, 14, 3) == Truth.UNKNOWN


def test_lifecycle_unknown_does_not_recover(region):
    rule = Rule("Hot", leaf(), recovery=leaf(op="<", value="78"))
    state = RuleState()

    def sample(raw, t):
        return state.advance(
            rule, {"a": parse_observation(region, raw, 99, t, t)}, t, 3
        )

    assert sample("90", 1) is None
    assert sample("90", 2) is None
    activation = sample("90", 3)
    assert activation[0] == "ALERT"
    assert sample("", 4) is None and state.incident_id == activation[1]
    assert sample("77", 5) is None
    assert sample("77", 6) is None
    assert sample("77", 7) == ("RECOVERY", activation[1])


def test_gap_duplicate_and_mixed_frames(region):
    rule = Rule("Hot", leaf())
    state = RuleState()
    obs = {"a": parse_observation(region, "90", 99, 1, 1)}
    state.advance(rule, obs, 1, 3)
    state.advance(rule, obs, 1, 3)
    assert state.count == 1
    obs["a"] = parse_observation(region, "90", 99, 10, 2)
    state.advance(rule, obs, 10, 3)
    assert state.count == 1
    obs["b"] = Observation("b", "90", 99, Quality.VALID, Decimal("90"), 10, 3)
    assert state.advance(rule, obs, 10, 3) is None


@pytest.mark.parametrize(
    "corners",
    [
        [[0, 0], [1, 1], [1, 0], [0, 1]],
        [[0, 0], [0.5, 0.5], [1, 0], [0, 1]],
        [[-0.1, 0], [1, 0], [1, 1], [0, 1]],
        [[0, 0]] * 4,
    ],
)
def test_bad_geometry(corners):
    with pytest.raises(ValueError):
        validate_corners(corners)


def test_normalized_geometry(region):
    for scale in (1, 2):
        frame = np.zeros((100 * scale, 200 * scale, 3), np.uint8)
        original, corrected = rectify(frame, region)
        assert original.shape == frame.shape
        assert corrected.shape[:2] == (100 * scale - 1, 200 * scale - 1)


def test_profile_roundtrip_disables_delivery(tmp_path):
    profile = demo_profile()
    profile.delivery_enabled = True
    path = tmp_path / "profile.json"
    save(profile, path)
    loaded = load(path)
    assert not loaded.delivery_enabled and loaded.regions == profile.regions
    assert "token" not in path.read_text()


def test_tree_limits(region):
    node = leaf()
    for _ in range(10):
        node = {"group": "ALL", "children": [node]}
    with pytest.raises(ValueError):
        validate_tree(node, {"a": region})


def test_outbox_order_restart_dedup(tmp_path):
    store = Store(tmp_path / "db")
    p = demo_profile()
    p.delivery_enabled = True
    p.chat_id = "123"
    rule = p.rules[0]
    store.enqueue(p, "ALERT", "Hot", "incident", rule, event_id="event1")
    store.enqueue(p, "ALERT", "Hot", "incident", rule, event_id="event1")
    store.enqueue(p, "RECOVERY", "Recovered", "incident", rule, event_id="event2")
    first = store.claim(p.id)
    assert first["event_id"] == "event1"
    assert store.claim(p.id) is None
    store = Store(tmp_path / "db")
    assert store.history(p.id)[1]["delivery"] == "uncertain"
    assert store.claim(p.id) is None
    store.delivered(first["seq"], "accepted")
    assert store.claim(p.id)["event_id"] == "event2"
    assert store.active(p.id) == {}


def test_data_coalesces(tmp_path):
    store = Store(tmp_path / "db")
    p = demo_profile()
    p.delivery_enabled = True
    p.chat_id = "1"
    p.routes.append("DATA")
    store.enqueue(p, "DATA", "old")
    store.enqueue(p, "DATA", "new")
    assert "new" in store.claim(p.id)["body"]
    assert store.claim(p.id) is None


def test_active_incident_survives_restart(tmp_path):
    p = demo_profile()
    store = Store(tmp_path / "db")
    store.enqueue(p, "ALERT", "Hot", "incident", p.rules[0])
    restored = Store(tmp_path / "db").active(p.id)
    assert restored == {p.rules[0].id: "incident"}
