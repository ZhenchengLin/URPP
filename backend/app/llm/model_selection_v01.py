"""Pick the local Ollama model that fits this computer's memory.

Tiers (total RAM -> model), largest first:

    >= 32 GiB  qwen3.5:27b   (17 GB download)
    >= 16 GiB  qwen3.5:9b    (6.6 GB)
    >=  8 GiB  qwen3.5:4b    (3.3 GB)
    otherwise  qwen3.5:2b    (1.9 GB)

The preferred tier is used when Ollama already has it. Otherwise the largest
installed model that still fits is used, so a missing download never breaks the
app. URPP_MODEL overrides the choice. Thresholds leave room for the operating
system and the context window; they are engineering defaults, not benchmarks.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from dataclasses import dataclass

GIB = 1024 ** 3

MODEL_TIERS_V01: tuple[tuple[int, str], ...] = (
    (32, "qwen3.5:27b"),
    (16, "qwen3.5:9b"),
    (8, "qwen3.5:4b"),
    (0, "qwen3.5:2b"),
)
SUPPORTED_MODELS_V01 = frozenset(model for _, model in MODEL_TIERS_V01)
_TAGS_ENDPOINT = "http://127.0.0.1:11434/api/tags"


@dataclass(frozen=True)
class ModelChoiceV01:
    model: str
    ram_gib: float
    preferred: str
    reason: str

    @property
    def pull_hint(self) -> str | None:
        if self.model == self.preferred:
            return None
        return f"For better answers on this computer, run: ollama pull {self.preferred}"


def total_ram_bytes_v01() -> int:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        pass
    try:  # macOS fallback
        return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                                  text=True, check=True, timeout=5).stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 8 * GIB


def installed_models_v01() -> set[str] | None:
    """Models Ollama has locally, or None if Ollama cannot be reached."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(_TAGS_ENDPOINT, timeout=3) as response:
            data = json.loads(response.read(1_000_000))
    except (OSError, ValueError):
        return None
    return {entry.get("name") for entry in data.get("models", []) if isinstance(entry, dict)}


def preferred_model_v01(ram_bytes: int) -> str:
    for minimum_gib, model in MODEL_TIERS_V01:
        if ram_bytes >= minimum_gib * GIB:
            return model
    return MODEL_TIERS_V01[-1][1]


def select_model_v01(
    *,
    ram_bytes: int | None = None,
    installed: set[str] | None = None,
    override: str | None = None,
    probe_installed: bool = True,
) -> ModelChoiceV01:
    ram = total_ram_bytes_v01() if ram_bytes is None else ram_bytes
    preferred = preferred_model_v01(ram)
    ram_gib = round(ram / GIB, 1)
    override = os.environ.get("URPP_MODEL") if override is None else override
    if override:
        if override not in SUPPORTED_MODELS_V01:
            raise ValueError(
                f"URPP_MODEL must be one of {sorted(SUPPORTED_MODELS_V01)}."
            )
        return ModelChoiceV01(override, ram_gib, preferred, "set by URPP_MODEL")
    if installed is None and probe_installed:
        installed = installed_models_v01()
    if installed is None or preferred in installed:
        reason = (f"{ram_gib} GB RAM -> {preferred}"
                  + ("" if installed is not None else " (Ollama not reachable to confirm)"))
        return ModelChoiceV01(preferred, ram_gib, preferred, reason)
    fitting = [model for minimum, model in MODEL_TIERS_V01 if ram >= minimum * GIB]
    for model in fitting:
        if model in installed:
            return ModelChoiceV01(
                model, ram_gib, preferred,
                f"{ram_gib} GB RAM prefers {preferred}, which is not installed; "
                f"using the largest installed model that fits, {model}",
            )
    return ModelChoiceV01(
        preferred, ram_gib, preferred,
        f"{ram_gib} GB RAM -> {preferred} (not installed yet)",
    )
