"""Bounded public GitHub release discovery, allowlisted downloads, and rate-limit state."""
import json
import http.client
from email.utils import parsedate_to_datetime
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from .common import read_bytes, ManagerError, atomic_json, read_json, file_hash
from .trust import verify, REPOSITORY


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def allowed(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.hostname not in (
        'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
        raise ManagerError('Unapproved update download location')


class Releases:
    def __init__(self, root, keys):
        self.root, self.keys = Path(root), keys

    def get(self, url, limit=1_000_000, destination=None):
        allowed(url)
        cooldown = self.root / 'state/network.json'
        if cooldown.exists() and read_json(cooldown).get('retry_after', 0) > time.time():
            raise ManagerError('GitHub rate limited this connection; retry later')
        request = urllib.request.Request(url, headers={'User-Agent': 'LiKeWatch-manager/1', 'Accept': 'application/vnd.github+json'})
        try:
            with urllib.request.build_opener(Redirects()).open(request, timeout=30) as response:
                if destination is not None:
                    total = 0
                    try:
                        with Path(destination).open('wb') as output:
                            while chunk := response.read(min(1024 * 1024, limit - total + 1)):
                                total += len(chunk)
                                if total > limit:
                                    raise ManagerError('Download exceeds expected size')
                                output.write(chunk)
                        return total
                    except BaseException:
                        Path(destination).unlink(missing_ok=True)
                        raise
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise ManagerError('Download exceeds expected size')
                return raw
        except urllib.error.HTTPError as error:
            if error.code in (403, 429):
                try:
                    retry = error.headers.get('Retry-After', '0')
                    try:
                        delay = float(retry)
                    except (TypeError, ValueError, OverflowError):
                        delay = parsedate_to_datetime(retry).timestamp() - time.time()
                    reset = max(time.time() + max(60, delay), float(error.headers.get('X-RateLimit-Reset', 0)))
                except (TypeError, ValueError, OverflowError):
                    reset = time.time() + 300
                atomic_json(cooldown, {'retry_after': reset})
            raise ManagerError(f'GitHub returned HTTP {error.code}; update status is unknown') from None
        except (OSError, TimeoutError, http.client.HTTPException):
            raise ManagerError('Update check unavailable: network, proxy, or TLS error') from None

    def check(self):
        if not self.keys:
            raise ManagerError('Production release signing is not configured; current installation remains usable')
        release = json.loads(self.get(f'https://api.github.com/repos/{REPOSITORY}/releases/latest'))
        if release.get('draft') or release.get('prerelease'):
            raise ManagerError('Release is not published stable')
        assets = {a['name']: a['browser_download_url'] for a in release.get('assets', [])}
        try:
            raw = self.get(assets['release-manifest.json'])
            sig = self.get(assets['release-manifest.sig'], 64)
        except KeyError:
            raise ManagerError('Published release has no signed source-update manifest') from None
        manifest = verify(raw, sig, self.keys)
        if release['tag_name'] != manifest['tag']:
            raise ManagerError('Release identity mismatch')
        folder = self.root / 'cache' / manifest['commit']
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'release-manifest.json').write_bytes(raw)
        (folder / 'release-manifest.sig').write_bytes(sig)
        atomic_json(folder / 'assets.json', assets)
        return manifest, folder

    def payload(self, metadata, folder):
        destination = folder / metadata['payload_name']
        if not destination.exists() or file_hash(destination) != metadata['payload_sha256']:
            assets = read_json(folder / 'assets.json')
            url = assets.get(metadata['payload_name']) or metadata.get('payload_url')
            if not url:
                raise ManagerError('Environment payload is not published')
            temporary = destination.with_suffix('.part')
            size = self.get(url, metadata['payload_size'], temporary)
            if size != metadata['payload_size'] or file_hash(temporary) != metadata['payload_sha256']:
                temporary.unlink(missing_ok=True)
                raise ManagerError('Environment payload failed integrity verification')
            temporary.replace(destination)
        return destination


class FixtureReleases:
    """Explicit signed local provider used only in clearly labelled test installations."""
    def __init__(self, folder, keys):
        self.folder, self.keys = Path(folder), keys

    def check(self):
        raw = read_bytes(self.folder / 'release-manifest.json')
        signature = read_bytes(self.folder / 'release-manifest.sig', 64)
        return verify(raw, signature, self.keys), self.folder
