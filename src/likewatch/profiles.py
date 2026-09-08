"""Validated, portable JSON profiles; imports never enable transmission."""

import json
import math
from decimal import Decimal
from pathlib import Path
from .domain import Profile, Region, Rule
from .imaging import validate_corners
from .rules import validate_tree


def validate(profile):
    if profile.schema != 1 or profile.source not in (
        "demo",
        "camera",
        "screen",
        "image",
    ):
        raise ValueError("Unsupported profile schema or source")
    if not isinstance(profile.device, int) or not 0 <= profile.device <= 100:
        raise ValueError("Device index must be 0–100")
    if not all(
        isinstance(x, (int, float)) and math.isfinite(x)
        for x in (profile.interval, profile.freshness)
    ):
        raise ValueError("Timing must be finite")
    if (
        not 0.2 <= profile.interval <= 3600
        or not profile.interval <= profile.freshness <= 86400
    ):
        raise ValueError(
            "Freshness must be at least the capture interval (0.2–3600 seconds)"
        )
    if len(profile.regions) > 32 or len(profile.rules) > 64:
        raise ValueError("Maximum 32 regions and 64 rules")
    if len({r.id for r in profile.regions}) != len(profile.regions) or len(
        {r.id for r in profile.rules}
    ) != len(profile.rules):
        raise ValueError("Duplicate region/rule IDs")
    for region in profile.regions:
        validate_corners(region.corners)
        if region.source_size and (
            len(region.source_size) != 2
            or any(not isinstance(x, int) or x < 5 for x in region.source_size)
        ):
            raise ValueError("Invalid source dimensions")
        if (
            not region.name.strip()
            or len(region.name) > 100
            or region.kind not in ("number", "text")
        ):
            raise ValueError("Invalid variable name or type")
        if region.preprocessing not in (
            "gray",
            "invert",
            "otsu",
            "adaptive",
        ) or region.psm not in (7, 8):
            raise ValueError("Unsupported OCR settings")
        if not 0 <= region.confidence <= 100 or not 0 <= region.aspect <= 20:
            raise ValueError("Invalid confidence or aspect ratio")
        for bound in (region.minimum, region.maximum):
            if bound and not Decimal(bound).is_finite():
                raise ValueError("Range limits must be finite")
        if (
            region.minimum
            and region.maximum
            and Decimal(region.minimum) > Decimal(region.maximum)
        ):
            raise ValueError("Minimum exceeds maximum")
    for rule in profile.rules:
        if (
            not rule.name.strip()
            or not 1 <= rule.confirm <= 100
            or not 1 <= rule.recover_confirm <= 100
        ):
            raise ValueError("Rules require a name and 1–100 confirmation samples")
        if not profile.interval <= rule.max_gap <= 86400:
            raise ValueError("Maximum sample gap must be at least the capture interval")
        validate_tree(rule.condition, {r.id: r for r in profile.regions})
        if rule.recovery is not None:
            validate_tree(rule.recovery, {r.id: r for r in profile.regions})
    if (
        not isinstance(profile.data_interval, int)
        or not 0 <= profile.data_interval <= 86400
    ):
        raise ValueError("Data interval must be 0 (disabled) through 86400 seconds")
    if any(
        route not in ("ALERT", "RECOVERY", "DATA", "SYSTEM", "TEST")
        for route in profile.routes
    ):
        raise ValueError("Unknown message route")
    if profile.topic_id and (
        not profile.topic_id.isdigit() or int(profile.topic_id) <= 0
    ):
        raise ValueError("Topic ID must be a positive integer")
    return profile


def load(path):
    if Path(path).stat().st_size > 1_000_000:
        raise ValueError("Profile exceeds 1 MB")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["regions"] = [Region(**r) for r in data.get("regions", [])]
    data["rules"] = [Rule(**r) for r in data.get("rules", [])]
    data["delivery_enabled"] = False
    return validate(Profile(**data))


def save(profile, path):
    validate(profile)
    destination = Path(path)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(profile.export(), indent=2), encoding="utf-8")
    temporary.replace(destination)


def demo_profile():
    a = Region(
        "Temperature",
        [[0.06, 0.29], [0.35, 0.29], [0.35, 0.44], [0.06, 0.44]],
        unit="°C",
    )
    b = Region(
        "Pressure", [[0.56, 0.29], [0.85, 0.29], [0.85, 0.44], [0.56, 0.44]], unit="kPa"
    )
    for r in (a, b):
        r.source_key = "demo:0:"
        r.source_size = [1000, 650]
    condition = {
        "group": "ALL",
        "children": [
            {"variable": a.id, "op": ">", "value": "80"},
            {"variable": b.id, "op": "<", "value": "20"},
        ],
    }
    recovery = {
        "group": "ANY",
        "children": [
            {"variable": a.id, "op": "<", "value": "78"},
            {"variable": b.id, "op": ">", "value": "22"},
        ],
    }
    return Profile(
        regions=[a, b],
        rules=[Rule("High temperature / low pressure", condition, recovery=recovery)],
    )
