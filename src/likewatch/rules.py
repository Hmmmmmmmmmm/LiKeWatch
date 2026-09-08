"""Bounded condition trees, three-valued evaluation, and incident transitions."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import operator
from .domain import uid


class Truth(Enum):
    FALSE = 0
    TRUE = 1
    UNKNOWN = 2


OPS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
    "contains": lambda text, fragment: fragment in text,
}


def validate_tree(node, regions, depth=0, budget=None):
    if budget is None:
        budget = [128]
    budget[0] -= 1
    if depth > 8 or budget[0] < 0 or not isinstance(node, dict):
        raise ValueError("Condition exceeds 8 levels or 128 nodes")
    if "group" in node:
        if (
            node["group"] not in ("ALL", "ANY")
            or not isinstance(node.get("children"), list)
            or not node["children"]
        ):
            raise ValueError("An AND/OR group needs at least one condition")
        for child in node["children"]:
            validate_tree(child, regions, depth + 1, budget)
    else:
        region = regions.get(node.get("variable"))
        if not region or node.get("op") not in OPS:
            raise ValueError("Unknown variable or comparison operator")
        value = node.get("value")
        if not isinstance(value, str) or len(value) > 128:
            raise ValueError("Comparison value must be a short string")
        if region.kind == "number":
            if node["op"] == "contains":
                raise ValueError("Text contains requires a text variable")
            try:
                number = Decimal(value)
                if not number.is_finite() or abs(number.adjusted()) > 1000:
                    raise ValueError("A finite numeric threshold is required")
            except InvalidOperation as error:
                raise ValueError("Invalid numeric threshold") from error
        elif node["op"] not in ("==", "!=", "contains"):
            raise ValueError("Text variables support ==, !=, and text contains")
        if node["op"] == "contains" and not value:
            raise ValueError("Enter non-empty text to search for")


def evaluate(node, observations, now, freshness):
    if "group" in node:
        children = [evaluate(c, observations, now, freshness) for c in node["children"]]
        decisive = Truth.FALSE if node["group"] == "ALL" else Truth.TRUE
        if decisive in children:
            return decisive
        if Truth.UNKNOWN in children:
            return Truth.UNKNOWN
        return Truth.TRUE if node["group"] == "ALL" else Truth.FALSE
    obs = observations.get(node["variable"])
    if obs is None or not obs.current(now, freshness):
        return Truth.UNKNOWN
    threshold = (
        Decimal(node["value"]) if isinstance(obs.value, Decimal) else node["value"]
    )
    return Truth.TRUE if OPS[node["op"]](obs.value, threshold) else Truth.FALSE


@dataclass
class RuleState:
    incident_id: str | None = None
    count: int = 0
    recovery_count: int = 0
    last_time: float | None = None
    last_frame: int | None = None
    truth: Truth = Truth.UNKNOWN

    @property
    def phase(self):
        return "ACTIVE" if self.incident_id else "PENDING" if self.count else "NORMAL"

    def advance(self, rule, observations, now, freshness):
        frames = {o.frame_id for o in observations.values()}
        frame = next(iter(frames)) if len(frames) == 1 else None
        if frame is None or frame == self.last_frame:
            return None
        self.last_frame = frame
        if (
            self.last_time is None
            or now - self.last_time > rule.max_gap
            or now < self.last_time
        ):
            self.count = self.recovery_count = 0
        self.last_time = now
        self.truth = evaluate(rule.condition, observations, now, freshness)
        if self.incident_id:
            recovery = (
                evaluate(rule.recovery, observations, now, freshness)
                if rule.recovery
                else (
                    Truth.TRUE
                    if self.truth == Truth.FALSE
                    else Truth.FALSE
                    if self.truth == Truth.TRUE
                    else Truth.UNKNOWN
                )
            )
            self.recovery_count = (
                self.recovery_count + 1 if recovery == Truth.TRUE else 0
            )
            if self.recovery_count >= rule.recover_confirm:
                incident = self.incident_id
                self.incident_id = None
                self.count = self.recovery_count = 0
                return "RECOVERY", incident
        else:
            self.count = self.count + 1 if self.truth == Truth.TRUE else 0
            if self.count >= rule.confirm:
                self.incident_id = uid()
                self.count = 0
                return "ALERT", self.incident_id
        return None


def describe(node, regions):
    if "group" in node:
        joiner = " AND " if node["group"] == "ALL" else " OR "
        return "(" + joiner.join(describe(c, regions) for c in node["children"]) + ")"
    region = regions.get(node["variable"])
    name = region.name if region else node["variable"]
    return f"{name} {node['op']} {node['value']}"


def explain(node, regions, observations, now, freshness, depth=0):
    result = evaluate(node, observations, now, freshness).name
    line = "  " * depth + f"{describe(node, regions)} → {result}"
    if "group" in node:
        return "\n".join(
            [line]
            + [
                explain(c, regions, observations, now, freshness, depth + 1)
                for c in node["children"]
            ]
        )
    obs = observations.get(node["variable"])
    return line + (
        f" (read: {obs.value}; {obs.quality.value})" if obs else " (unavailable)"
    )
