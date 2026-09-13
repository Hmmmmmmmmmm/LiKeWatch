"""Typed protocol records and strict, dependency-free JSON shape validation."""
import re
import math
import types
from typing import Annotated, Any, Literal, NotRequired, TypedDict, Union, get_args, get_origin, get_type_hints, is_typeddict
from .common import ManagerError

Sha256 = Annotated[str, r'^[a-f0-9]{64}$']
Commit = Annotated[str, r'^[a-f0-9]{40}$']
Nonce = Annotated[str, r'^[a-f0-9]{32}$']
SchemaRange = Annotated[list[int], 'schema-range']
Positive = Annotated[int, 'positive']


class Payload(TypedDict):
    environment_id: Sha256
    lock_sha256: Sha256
    payload_sha256: Sha256
    payload_name: str
    payload_size: int
    python: Literal['3.13']
    payload_url: NotRequired[str]


class ReleaseManifest(TypedDict):
    schema: Literal[1]
    repository: str
    version: str
    tag: str
    commit: Commit
    channel: Literal['stable']
    sequence: Positive
    issued: int
    expires: int
    manager_protocol: int
    profile_read: SchemaRange
    database_read: SchemaRange
    platforms: dict[str, Payload]
    notes: NotRequired[str]


class Deployment(TypedDict):
    commit: Commit
    version: str
    environment_id: Sha256
    manifest_digest: Sha256
    profile_read: SchemaRange
    database_read: SchemaRange


class DeploymentState(TypedDict):
    schema: Literal[1]
    generation: Positive
    active: Deployment
    previous: Deployment | None
    highest_sequence: Positive


class UpdatePlan(TypedDict):
    schema: Literal[1]
    id: Nonce
    generation: Positive
    candidate: Deployment
    sequence: Positive
    phase: Literal['prepared', 'validated']
    created: float
    validation: NotRequired[str]


class TransactionJournal(TypedDict):
    schema: Literal[1]
    phase: Literal['trial', 'committed']
    generation: Positive
    candidate: NotRequired[Deployment]


class LaunchContext(TypedDict):
    schema: Literal[1]
    source_root: str
    native_root: str
    commit: Commit
    environment_id: Sha256
    install_root: str
    manager_python: str
    session: Nonce
    nonce: Nonce
    transaction: str
    health_file: str
    request_file: str
    activated_file: str
    test_mode: bool
    supervised: bool
    data_root: NotRequired[str]
    settings_file: NotRequired[str]
    log_root: NotRequired[str]


class HealthReport(TypedDict):
    schema: Literal[1]
    pid: Positive
    nonce: Nonce
    session: Nonce
    transaction: str
    commit: Commit
    environment_id: Sha256
    source: str
    python: str
    status: Literal['ready']


class ManagerResult(TypedDict):
    schema: Literal[1]
    ok: bool
    result: NotRequired[dict[str, Any]]
    error: NotRequired[str]


def validate(value, annotation, path='record'):
    """Check protocol shapes; trust, ranges, containment and transitions add semantic checks."""
    origin, arguments = get_origin(annotation), get_args(annotation)
    fail = lambda: ManagerError(f'Invalid {path}; unsupported or malformed protocol record')
    if annotation is Any:
        return value
    if origin is NotRequired:
        return validate(value, arguments[0], path)
    if origin is Annotated:
        validate(value, arguments[0], path)
        constraint = arguments[1]
        if constraint == 'schema-range':
            if len(value) != 2 or not 0 <= value[0] <= value[1]:
                raise fail()
        elif constraint == 'positive':
            if value < 1:
                raise fail()
        elif not re.fullmatch(constraint, value):
            raise fail()
    elif origin in (Union, types.UnionType):
        for choice in arguments:
            try:
                return validate(value, choice, path)
            except ManagerError:
                continue
        raise fail()
    elif origin is Literal:
        if not any(type(value) is type(choice) and value == choice for choice in arguments):
            raise fail()
    elif is_typeddict(annotation):
        fields = get_type_hints(annotation, include_extras=True)
        if not isinstance(value, dict) or not annotation.__required_keys__ <= value.keys() or value.keys() - fields.keys():
            raise fail()
        for name, item in value.items():
            validate(item, fields[name], path + '.' + name)
    elif origin is list:
        if not isinstance(value, list):
            raise fail()
        for item in value:
            validate(item, arguments[0], path + '[]')
    elif origin is dict:
        if not isinstance(value, dict):
            raise fail()
        for key, item in value.items():
            validate(key, arguments[0], path + '.key')
            validate(item, arguments[1], path + '[]')
    elif annotation is float:
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            raise fail()
    elif type(value) is not annotation:
        raise fail()
    return value


def json_schema(annotation):
    origin, arguments = get_origin(annotation), get_args(annotation)
    if annotation is Any:
        return {}
    if origin is NotRequired:
        return json_schema(arguments[0])
    if origin is Annotated:
        if arguments[1] == 'schema-range':
            return {'type': 'array', 'items': {'type': 'integer', 'minimum': 0}, 'minItems': 2, 'maxItems': 2, 'description': 'Inclusive ordered schema range'}
        if arguments[1] == 'positive':
            return {'type': 'integer', 'minimum': 1}
        return json_schema(arguments[0]) | {'pattern': arguments[1]}
    if origin in (Union, types.UnionType):
        return {'anyOf': [json_schema(choice) for choice in arguments]}
    if origin is Literal:
        return {'enum': list(arguments), **json_schema(type(arguments[0]))}
    if is_typeddict(annotation):
        return {'type': 'object', 'properties': {name: json_schema(kind) for name, kind in get_type_hints(annotation, include_extras=True).items()},
                'required': sorted(annotation.__required_keys__), 'additionalProperties': False}
    if origin is list:
        return {'type': 'array', 'items': json_schema(arguments[0])}
    if origin is dict:
        return {'type': 'object', 'additionalProperties': json_schema(arguments[1])}
    return {'type': {str: 'string', int: 'integer', float: 'number', bool: 'boolean', type(None): 'null'}[annotation]}


RECORDS = (ReleaseManifest, Deployment, DeploymentState, UpdatePlan, TransactionJournal, LaunchContext, HealthReport, ManagerResult)
