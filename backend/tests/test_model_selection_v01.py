"""RAM-based local model selection (offline)."""

import pytest

from app.llm.model_selection_v01 import GIB, select_model_v01


@pytest.mark.parametrize("ram_gib, expected", [
    (4, "qwen3.5:2b"), (8, "qwen3.5:4b"), (15.9, "qwen3.5:4b"),
    (16, "qwen3.5:9b"), (31, "qwen3.5:9b"), (32, "qwen3.5:27b"), (64, "qwen3.5:27b"),
])
def test_preferred_tier_by_ram(ram_gib, expected):
    choice = select_model_v01(ram_bytes=int(ram_gib * GIB), installed={expected}, override="")
    assert choice.model == expected
    assert choice.pull_hint is None


def test_falls_back_to_largest_installed_model_that_fits():
    choice = select_model_v01(ram_bytes=16 * GIB, installed={"qwen3.5:2b", "qwen3.5:4b"},
                              override="")
    assert choice.model == "qwen3.5:4b"
    assert choice.preferred == "qwen3.5:9b"
    assert choice.pull_hint == "For better answers on this computer, run: ollama pull qwen3.5:9b"


def test_never_picks_an_installed_model_that_does_not_fit():
    choice = select_model_v01(ram_bytes=8 * GIB, installed={"qwen3.5:27b"}, override="")
    assert choice.model == "qwen3.5:4b"  # preferred, reported as not installed


def test_override_wins_and_is_validated():
    assert select_model_v01(ram_bytes=8 * GIB, installed=set(),
                            override="qwen3.5:9b").model == "qwen3.5:9b"
    with pytest.raises(ValueError):
        select_model_v01(ram_bytes=8 * GIB, installed=set(), override="gpt-oss:120b")


def test_ollama_unreachable_uses_preferred():
    choice = select_model_v01(ram_bytes=16 * GIB, installed=None, override="",
                              probe_installed=False)
    assert choice.model == "qwen3.5:9b"
