"""Collect installed distribution licenses and a version inventory for packaging."""

from importlib.metadata import distributions
from pathlib import Path
import json
import shutil


def collect(root):
    destination = root / "build/licenses"
    destination.mkdir(parents=True, exist_ok=True)
    inventory = []
    for distribution in distributions():
        name = distribution.metadata["Name"]
        if name.lower() == "likewatch":
            continue
        inventory.append(
            {
                "name": name,
                "version": distribution.version,
                "license": distribution.metadata.get("License-Expression")
                or distribution.metadata.get("License", ""),
                "homepage": distribution.metadata.get("Home-page", ""),
            }
        )
        for item in distribution.files or []:
            path = Path(item)
            if any(
                key in path.name.lower() for key in ("license", "copying", "copyright")
            ):
                original = Path(distribution.locate_file(item))
                if original.is_file() and original.stat().st_size < 2_000_000:
                    target = destination / name / path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, target)
    (destination / "inventory.json").write_text(
        json.dumps(inventory, indent=2), encoding="utf-8"
    )
