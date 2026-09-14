"""Release authority: verify exact metadata bytes before interpreting candidate data."""
import base64
import json
import re
import time
from packaging.version import Version, InvalidVersion
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from .common import ManagerError, identifier
from . import PROTOCOL
from .models import ReleaseManifest, validate

REPOSITORY = 'Hmmmmmmmmmm/LiKeWatch'


def verify(raw, signature, public_keys, *, fresh=True, repository=REPOSITORY):
    if len(raw) > 1_000_000 or len(signature) != 64:
        raise ManagerError('Invalid signed metadata size')
    valid = False
    for key in public_keys:
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(key, validate=True)).verify(signature, raw)
            valid = True
            break
        except (ValueError, InvalidSignature):
            # cryptography exceptions must not expose key material.
            continue
    if not valid:
        raise ManagerError('Release signature is missing or untrusted')
    try:
        m = validate(json.loads(raw), ReleaseManifest)
        if m['schema'] != 1 or m['repository'] != repository or m['channel'] != 'stable':
            raise ValueError()
        version = Version(m['version'])
        if version.is_prerelease or version.is_devrelease or version.local:
            raise ValueError()
        if m['tag'] not in ('v' + str(version), 'v' + '.'.join(str(x) for x in version.release[:2])):
            raise ValueError()
        identifier(m['commit'], r'[a-f0-9]{40}')
        if type(m['sequence']) is not int or m['sequence'] < 1:
            raise ValueError()
        if m['manager_protocol'] > PROTOCOL:
            raise ManagerError('This update needs a newer full LiKeWatch installer')
        if m['manager_protocol'] != 1 or not m['issued'] < m['expires']:
            raise ValueError()
        if fresh and not m['issued'] - 300 <= time.time() <= m['expires']:
            raise ManagerError('Update metadata expired or system clock is incorrect')
        for name in ('profile_read', 'database_read'):
            if len(m[name]) != 2 or not all(type(v) is int for v in m[name]) or m[name][0] > m[name][1]:
                raise ValueError()
        for platform, payload in m['platforms'].items():
            if platform not in ('win-64', 'osx-arm64'):
                raise ValueError()
            identifier(payload['environment_id'])
            identifier(payload['lock_sha256'])
            identifier(payload['payload_sha256'])
            if payload['python'] != '3.13' or type(payload['payload_size']) is not int or not 0 < payload['payload_size'] < 3_000_000_000:
                raise ValueError()
            identifier(payload['payload_name'], r'[A-Za-z0-9_.-]+')
            if 'payload_url' in payload and not re.fullmatch(re.escape(f'https://github.com/{repository}/releases/download/') + r'v[0-9]+\.[0-9]+(?:\.[0-9]+)?/' + re.escape(payload['payload_name']), payload['payload_url']):
                raise ValueError()
        if not m['platforms']:
            raise ValueError()
    except ManagerError:
        raise
    except (KeyError, TypeError, ValueError, InvalidVersion):
        raise ManagerError('Unsupported or malformed release manifest') from None
    return m
