"""Build on the target OS. Windows portable EXE; macOS application and DMG."""

import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
os.environ.setdefault("PYINSTALLER_CONFIG_DIR", str(root / "build/pyinstaller-cache"))
from licenses import collect
from likewatch import __version__

dist = Path(os.environ.get("LIKEWATCH_BUILD_DIR", str(root / "dist"))).resolve()

if sys.platform == "darwin":
    subprocess.run(["/usr/bin/swiftc", str(root / "assets/authenticate.swift"),
                    "-o", str(root / "assets/native-auth")], check=True)
collect(root)
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--workpath",
        os.environ.get("LIKEWATCH_WORK_DIR", str(root / "build")),
        "--distpath",
        str(dist),
        str(root / "LiKeWatch.spec"),
    ],
    cwd=root,
    check=True,
)
if sys.platform == "darwin":
    app = dist / "LiKeWatch.app"
    executable = app / "Contents/MacOS/LiKeWatch"
    subprocess.run(
        [
            str(executable),
            "--self-test",
            "--ui-stress",
            "--report",
            str(dist / "native-smoke.json"),
        ],
        check=True,
        timeout=120,
    )
    staging = Path(os.environ.get("LIKEWATCH_WORK_DIR", str(root / "build"))) / "dmg"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app, staging / "LiKeWatch.app", dirs_exist_ok=True, symlinks=True)
    link = staging / "Applications"
    if not link.exists():
        link.symlink_to("/Applications")
    shutil.copy2(root / "docs/INSTALL.md", staging / "INSTALL.txt")
    artifact = dist / f"LiKeWatch-{__version__}-macOS-{platform.machine()}.dmg"
    subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            f"LiKeWatch {__version__}",
            "-srcfolder",
            str(staging),
            "-ov",
            "-format",
            "UDZO",
            str(artifact),
        ],
        check=True,
    )
else:
    executable = dist / "LiKeWatch.exe"
    subprocess.run(
        [
            str(executable),
            "--self-test",
            "--ui-stress",
            "--report",
            str(dist / "native-smoke.json"),
        ],
        check=True,
        timeout=180,
    )
    artifact = dist / f"LiKeWatch-{__version__}-Windows-x64-portable.exe"
    executable.rename(artifact)
checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
(dist / (artifact.name + ".sha256")).write_text(f"{checksum}  {artifact.name}\n")
print(f"Built and smoke-tested: {artifact}")
