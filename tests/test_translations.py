"""Generated translation/icon files must be current and cover the catalog."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from custom_components.sony_adcp_projector.catalog import FEATURES, LENS_KEYS

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "custom_components" / "sony_adcp_projector" / "translations" / "en.json"


def test_generated_files_current() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "script" / "generate_translations.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_every_feature_named() -> None:
    entity = json.loads(EN.read_text())["entity"]
    for feature in FEATURES:
        assert any(feature.tkey in entity[platform] for platform in entity), feature.key
    for key in LENS_KEYS:
        assert key in entity["button"]
