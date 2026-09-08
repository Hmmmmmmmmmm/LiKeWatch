"""Serializable contracts. This module has no UI, imaging, or network imports."""
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from enum import StrEnum
import math
import re
import uuid


def uid():
    return str(uuid.uuid4())


class Quality(StrEnum):
    VALID = "VALID"
    EMPTY = "EMPTY"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    PARSE_ERROR = "PARSE_ERROR"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    STALE = "STALE"
    SOURCE_ERROR = "SOURCE_ERROR"
    OCR_ERROR = "OCR_ERROR"


@dataclass
class Region:
    name: str
    corners: list[list[float]]
    id: str = field(default_factory=uid)
    kind: str = "number"
    unit: str = ""
    preprocessing: str = "gray"
    confidence: float = 50
    minimum: str = ""
    maximum: str = ""
    psm: int = 7
    aspect: float = 0
    source_key: str = ""
    source_size: list[int] = field(default_factory=list)


@dataclass
class Observation:
    region_id: str
    raw: str
    confidence: float
    quality: Quality
    value: Decimal | str | None
    timestamp: float
    frame_id: int

    def current(self, now, freshness):
        return self.quality == Quality.VALID and 0 <= now - self.timestamp <= freshness


NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)


def parse_observation(region, raw, confidence, timestamp, frame_id):
    text = raw.strip()
    value = None
    if not text:
        quality = Quality.EMPTY
    elif not math.isfinite(confidence) or confidence < region.confidence:
        quality = Quality.LOW_CONFIDENCE
    elif region.kind == "number":
        if not NUMBER.fullmatch(text) or len(text) > 128:
            quality = Quality.PARSE_ERROR
        else:
            value = Decimal(text)
            if not value.is_finite() or abs(value.adjusted()) > 1000:
                quality = Quality.PARSE_ERROR
            elif ((region.minimum and value < Decimal(region.minimum)) or
                  (region.maximum and value > Decimal(region.maximum))):
                quality = Quality.OUT_OF_RANGE
            else:
                quality = Quality.VALID
    elif not text.isascii():
        quality = Quality.PARSE_ERROR
    else:
        quality, value = Quality.VALID, text
    if quality != Quality.VALID:
        value = None
    return Observation(region.id, raw, confidence, quality, value, timestamp, frame_id)


@dataclass
class Rule:
    name: str
    condition: dict
    id: str = field(default_factory=uid)
    recovery: dict | None = None
    confirm: int = 3
    recover_confirm: int = 3
    max_gap: float = 2


@dataclass
class Profile:
    schema: int = 1
    id: str = field(default_factory=uid)
    source: str = "demo"
    device: int = 0
    image_path: str = ""
    interval: float = 1
    freshness: float = 3
    regions: list[Region] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    chat_id: str = ""
    topic_id: str = ""
    delivery_enabled: bool = False
    data_interval: int = 0
    routes: list[str] = field(default_factory=lambda: ["ALERT", "RECOVERY", "TEST"])

    def source_key(self):
        return f'{self.source}:{self.device}:{self.image_path if self.source == "image" else ""}'

    def export(self):
        data = asdict(self)
        data["delivery_enabled"] = False
        return data
