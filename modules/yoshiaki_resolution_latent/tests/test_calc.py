"""
Unit tests for calc.py (spec ch.7). Run from the repo root:

    pytest modules/yoshiaki_resolution_latent/tests

cases.json is shared with the JS implementation (js/yoshiaki-resolution-latent-calc.js),
so both give the same results for the same inputs.
"""

import importlib.util
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# Load calc.py directly so the test does not import the package __init__ chain
# (presets.py would create the TOML file; nodes.py needs ComfyUI / torch).
_spec = importlib.util.spec_from_file_location("yrl_calc", os.path.join(HERE, "..", "calc.py"))
calc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(calc)

with open(os.path.join(HERE, "cases.json"), encoding="utf-8") as f:
    CASES = json.load(f)


@pytest.mark.parametrize("case", CASES, ids=[f"{c['text']}-{c['orientation']}-m{c['multiple']}" for c in CASES])
def test_compute(case):
    args = (case["text"], case["orientation"], case["mp"], case["multiple"], case["req"])
    kwargs = {"mp_range": case.get("mp_range")}
    if case.get("error"):
        with pytest.raises(calc.CalcError):
            calc.compute(*args, **kwargs)
        return
    res = calc.compute(*args, **kwargs)
    assert (res["width"], res["height"]) == (case["width"], case["height"])
    assert len(res["warnings"]) == case["warnings"], res["warnings"]
    if "multiple_out" in case:
        assert res["multiple"] == case["multiple_out"]


def test_round_half_up():
    # 62.5 -> 63 (Python's round() would give 62)
    assert calc.round_to(1000, 16) == 1008
    assert calc.round_to(8, 16) == 16


def test_required_multiple():
    assert calc.required_multiple(16, 8, generic=False) == 16
    assert calc.required_multiple(16, 16, generic=False) == 16
    assert calc.required_multiple(12, 8, generic=False) == 24
    assert calc.required_multiple(16, 8, generic=True) == 8


def test_error_message_for_x_typo():
    with pytest.raises(calc.CalcError, match=":"):
        calc.parse_spec("16x9")
