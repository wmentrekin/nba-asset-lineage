from __future__ import annotations

import json
from pathlib import Path
from collections.abc import Iterable

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_json_fixture(name: str):
    return json.loads((FIXTURES_DIR / name).read_text())


def evidence_module(name: str):
    return pytest.importorskip(f"evidence.{name}")


def get_callable(module, *names: str):
    for name in names:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    available = ", ".join(sorted(attr for attr in dir(module) if not attr.startswith("_")))
    pytest.fail(
        f"{module.__name__} must expose one of: {', '.join(names)}. "
        f"Available public names: {available}"
    )


def as_list(result, *candidate_attrs: str):
    if isinstance(result, list):
        return result
    if isinstance(result, tuple):
        for item in result:
            if isinstance(item, list):
                return item
    if isinstance(result, dict):
        for attr in candidate_attrs:
            value = result.get(attr)
            if isinstance(value, list):
                return value
    if isinstance(result, Iterable) and not isinstance(result, (str, bytes, dict)):
        return list(result)
    for attr in candidate_attrs:
        value = getattr(result, attr, None)
        if isinstance(value, list):
            return value
    pytest.fail(f"Could not extract a list from result: {result!r}")


def get_value(obj, *candidate_attrs: str):
    if isinstance(obj, dict):
        for attr in candidate_attrs:
            if attr in obj:
                return obj[attr]
    for attr in candidate_attrs:
        if hasattr(obj, attr):
            return getattr(obj, attr)
    pytest.fail(f"Could not extract any of {candidate_attrs!r} from {obj!r}")


def call_validate(validate_fn, source_records, normalized_claims, overrides):
    try:
        return validate_fn(
            source_records=source_records,
            normalized_claims=normalized_claims,
            overrides=overrides,
        )
    except TypeError:
        return validate_fn(
            {
                "source_records": source_records,
                "normalized_claims": normalized_claims,
                "overrides": overrides,
            }
        )


def call_with_fallbacks(fn, *attempts):
    last_error = None
    for args, kwargs in attempts:
        try:
            return fn(*args, **kwargs)
        except TypeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    pytest.fail("No call attempts were provided")
