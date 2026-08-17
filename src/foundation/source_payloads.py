"""Immutable, local source bundles used by the refresh preview and runner.

This module deliberately has no HTTP or database dependency.  Capture callers inject
their fetcher, while every later consumer validates and reads these exact bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping


SOURCE_BUNDLE_SCHEMA_VERSION = "source_bundle_v1"
MANIFEST_FILE_NAME = "manifest.json"
SUPPORTED_SOURCE_KINDS = frozenset(
    {"nba_player_movement", "bref_transactions", "bref_draft", "official_releases"}
)
RESPONSE_METADATA_FIELDS = frozenset(
    {"status_code", "final_url", "content_type", "content_encoding", "content_length", "etag", "last_modified"}
)
_REFRESH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_STABLE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class SourceBundleError(ValueError):
    """Raised before a bundle can be normalized or used by a later writer."""


@dataclass(frozen=True)
class CapturedResponse:
    stable_key: str
    source_url: str
    media_type: str
    body: bytes
    response_metadata: Mapping[str, object] | None = None


@dataclass(frozen=True)
class SourceBundle:
    path: Path
    manifest: dict[str, object]
    bodies: dict[str, bytes]

    @property
    def digest(self) -> str:
        return str(self.manifest["bundle_sha256"])


def canonical_json_bytes(value: object) -> bytes:
    """Return the closed, reproducible JSON encoding used for bundle manifests."""
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SourceBundleError("Bundle metadata must contain only JSON values.") from exc


def raw_body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _bundle_digest(manifest_without_digest: dict[str, object]) -> str:
    return hashlib.sha256(
        b"nba-asset-lineage:source-bundle:v1\0" + canonical_json_bytes(manifest_without_digest)
    ).hexdigest()


def _utc_timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise SourceBundleError("captured_at must be a UTC RFC3339 timestamp rounded to seconds.")
    return value


def _validate_relative_body_path(value: object) -> str:
    if not isinstance(value, str):
        raise SourceBundleError("relative_body_path must be a string.")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise SourceBundleError(f"Unsafe relative body path: {value!r}")
    if path.parts[0] != "bodies" or len(path.parts) != 2:
        raise SourceBundleError("Body paths must be direct files under bodies/.")
    return value


def _validate_metadata(value: Mapping[str, object] | None) -> dict[str, object]:
    result = dict(value or {})
    extra = set(result).difference(RESPONSE_METADATA_FIELDS)
    if extra:
        raise SourceBundleError(f"Unsupported response metadata: {sorted(extra)}")
    # JSON encoding also rejects unserializable values, before anything is committed.
    canonical_json_bytes(result)
    return result


def _validate_private_directory(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise SourceBundleError(f"Operational path must be a real directory: {path}")
    if info.st_mode & 0o077:
        raise SourceBundleError(f"Operational directory has permissive mode: {path}")


def _write_private_file(path: Path, body: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # fdopen owns the descriptor after success; this only covers os.fdopen failure.
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def capture_source_bundle(
    bundle_path: Path,
    *,
    source_kind: str,
    source_scope: Mapping[str, object],
    normalization_config: Mapping[str, object],
    responses: list[CapturedResponse],
    captured_at: str | None = None,
) -> SourceBundle:
    """Atomically create a bundle from already-captured response bytes.

    The parent must be a private local operational directory.  A failed capture
    never leaves the requested final directory behind.
    """
    if source_kind not in SUPPORTED_SOURCE_KINDS:
        raise SourceBundleError(f"Unsupported source_kind: {source_kind}")
    if bundle_path.exists() or bundle_path.is_symlink():
        raise SourceBundleError(f"Refusing to overwrite existing bundle: {bundle_path}")
    parent = bundle_path.parent
    _validate_private_directory(parent)
    if not isinstance(source_scope, Mapping) or not source_scope:
        raise SourceBundleError("source_scope must be a non-empty object.")
    if not isinstance(normalization_config, Mapping):
        raise SourceBundleError("normalization_config must be an object.")
    canonical_json_bytes(dict(source_scope))
    canonical_json_bytes(dict(normalization_config))

    seen_keys: set[str] = set()
    manifest_items: list[dict[str, object]] = []
    normalized_responses: list[CapturedResponse] = []
    for response in responses:
        if not _STABLE_KEY.fullmatch(response.stable_key):
            raise SourceBundleError(f"Invalid stable_key: {response.stable_key!r}")
        if response.stable_key in seen_keys:
            raise SourceBundleError(f"Duplicate stable_key: {response.stable_key}")
        if not isinstance(response.source_url, str) or not response.source_url:
            raise SourceBundleError("source_url is required.")
        if not isinstance(response.media_type, str) or not response.media_type:
            raise SourceBundleError("media_type is required.")
        if not isinstance(response.body, bytes):
            raise SourceBundleError("Captured bodies must be bytes.")
        seen_keys.add(response.stable_key)
        relative_path = f"bodies/{response.stable_key}.bin"
        manifest_items.append(
            {
                "stable_key": response.stable_key,
                "source_url": response.source_url,
                "media_type": response.media_type,
                "relative_body_path": relative_path,
                "byte_length": len(response.body),
                "response_metadata": _validate_metadata(response.response_metadata),
                "body_sha256": raw_body_sha256(response.body),
            }
        )
        normalized_responses.append(response)
    if not manifest_items:
        raise SourceBundleError("A source bundle must contain at least one item.")
    manifest_items.sort(key=lambda item: str(item["stable_key"]))
    base_manifest: dict[str, object] = {
        "schema_version": SOURCE_BUNDLE_SCHEMA_VERSION,
        "source_kind": source_kind,
        "source_scope": dict(source_scope),
        "captured_at": _utc_timestamp(captured_at),
        "normalization_config": dict(normalization_config),
        "items": manifest_items,
    }
    manifest = {**base_manifest, "bundle_sha256": _bundle_digest(base_manifest)}

    temporary = parent / f".{bundle_path.name}.tmp-{uuid.uuid4().hex}"
    try:
        os.mkdir(temporary, 0o700)
        bodies_dir = temporary / "bodies"
        os.mkdir(bodies_dir, 0o700)
        by_key = {response.stable_key: response for response in normalized_responses}
        for item in manifest_items:
            response = by_key[str(item["stable_key"])]
            _write_private_file(temporary / str(item["relative_body_path"]), response.body)
        _write_private_file(temporary / MANIFEST_FILE_NAME, canonical_json_bytes(manifest))
        os.replace(temporary, bundle_path)
    except BaseException:
        if temporary.exists() and not temporary.is_symlink():
            shutil.rmtree(temporary)
        raise
    return load_source_bundle(bundle_path, expected_digest=str(manifest["bundle_sha256"]))


def capture_source_bundle_from_fetcher(
    bundle_path: Path,
    *,
    source_kind: str,
    source_scope: Mapping[str, object],
    normalization_config: Mapping[str, object],
    requests: list[tuple[str, str, str]],
    fetcher: Callable[[str], bytes | tuple[bytes, Mapping[str, object] | None]],
    captured_at: str | None = None,
) -> SourceBundle:
    """Capture each configured URL once with an injected fetcher, then lock bytes."""
    responses: list[CapturedResponse] = []
    for stable_key, source_url, media_type in requests:
        fetched = fetcher(source_url)
        body, metadata = fetched if isinstance(fetched, tuple) else (fetched, None)
        responses.append(CapturedResponse(stable_key, source_url, media_type, body, metadata))
    return capture_source_bundle(
        bundle_path,
        source_kind=source_kind,
        source_scope=source_scope,
        normalization_config=normalization_config,
        responses=responses,
        captured_at=captured_at,
    )


def load_source_bundle(
    bundle_path: Path,
    *,
    expected_digest: str | None = None,
    expected_source_kind: str | None = None,
    expected_source_scope: Mapping[str, object] | None = None,
) -> SourceBundle:
    """Validate every manifest invariant and return exact raw bytes for normalization."""
    _validate_private_directory(bundle_path)
    manifest_path = bundle_path / MANIFEST_FILE_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SourceBundleError("Bundle manifest is missing or unsafe.")
    manifest_info = manifest_path.lstat()
    if manifest_info.st_mode & 0o077 or manifest_info.st_nlink != 1:
        raise SourceBundleError("Bundle manifest has unsafe mode or link count.")
    try:
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceBundleError("Bundle manifest is not valid UTF-8 JSON.") from exc
    required = {
        "schema_version", "source_kind", "source_scope", "captured_at", "normalization_config", "items", "bundle_sha256"
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise SourceBundleError("Bundle manifest fields do not match the closed schema.")
    if manifest_raw != canonical_json_bytes(manifest):
        raise SourceBundleError("Bundle manifest is not canonically encoded.")
    if manifest["schema_version"] != SOURCE_BUNDLE_SCHEMA_VERSION:
        raise SourceBundleError("Unsupported bundle schema version.")
    source_kind = manifest["source_kind"]
    if source_kind not in SUPPORTED_SOURCE_KINDS:
        raise SourceBundleError("Unsupported bundle source kind.")
    if expected_source_kind is not None and source_kind != expected_source_kind:
        raise SourceBundleError("Bundle source kind does not match requested loader.")
    if not isinstance(manifest["source_scope"], dict) or not manifest["source_scope"]:
        raise SourceBundleError("Bundle source scope is invalid.")
    if expected_source_scope is not None and dict(expected_source_scope) != manifest["source_scope"]:
        raise SourceBundleError("Bundle source scope does not match requested loader.")
    if not isinstance(manifest["captured_at"], str):
        raise SourceBundleError("Bundle capture timestamp is invalid.")
    _utc_timestamp(manifest["captured_at"])
    if not isinstance(manifest["normalization_config"], dict):
        raise SourceBundleError("Bundle normalization config is invalid.")
    canonical_json_bytes(manifest["source_scope"])
    canonical_json_bytes(manifest["normalization_config"])
    items = manifest["items"]
    if not isinstance(items, list) or not items:
        raise SourceBundleError("Bundle must contain items.")
    bodies: dict[str, bytes] = {}
    previous_key = ""
    seen_paths: set[str] = set()
    required_item = {"stable_key", "source_url", "media_type", "relative_body_path", "byte_length", "response_metadata", "body_sha256"}
    for item in items:
        if not isinstance(item, dict) or set(item) != required_item:
            raise SourceBundleError("Bundle item fields do not match the closed schema.")
        stable_key = item["stable_key"]
        if not isinstance(stable_key, str) or not _STABLE_KEY.fullmatch(stable_key) or stable_key <= previous_key:
            raise SourceBundleError("Bundle items must have unique, sorted stable keys.")
        previous_key = stable_key
        relative_path = _validate_relative_body_path(item["relative_body_path"])
        if relative_path in seen_paths:
            raise SourceBundleError("Duplicate bundle body path.")
        seen_paths.add(relative_path)
        if relative_path != f"bodies/{stable_key}.bin":
            raise SourceBundleError("Bundle body path does not match stable key.")
        if not isinstance(item["source_url"], str) or not item["source_url"] or not isinstance(item["media_type"], str):
            raise SourceBundleError("Bundle item URL or media type is invalid.")
        if not isinstance(item["byte_length"], int) or item["byte_length"] < 0:
            raise SourceBundleError("Bundle item byte length is invalid.")
        _validate_metadata(item["response_metadata"] if isinstance(item["response_metadata"], dict) else None)
        if not isinstance(item["body_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["body_sha256"]):
            raise SourceBundleError("Bundle item digest is invalid.")
        body_path = bundle_path / relative_path
        if body_path.is_symlink() or not body_path.is_file():
            raise SourceBundleError("Bundle body is missing or unsafe.")
        body_info = body_path.lstat()
        if body_info.st_mode & 0o077 or body_info.st_nlink != 1:
            raise SourceBundleError("Bundle body has unsafe mode or link count.")
        body = body_path.read_bytes()
        if len(body) != item["byte_length"] or raw_body_sha256(body) != item["body_sha256"]:
            raise SourceBundleError("Bundle body does not match its manifest digest.")
        bodies[stable_key] = body
    bodies_dir = bundle_path / "bodies"
    if bodies_dir.is_symlink() or not bodies_dir.is_dir():
        raise SourceBundleError("Bundle bodies directory is missing or unsafe.")
    body_dir_info = bodies_dir.lstat()
    if body_dir_info.st_mode & 0o077:
        raise SourceBundleError("Bundle bodies directory has a permissive mode.")
    actual_body_paths = {entry.relative_to(bundle_path).as_posix() for entry in bodies_dir.iterdir()}
    if actual_body_paths != seen_paths:
        raise SourceBundleError("Bundle contains missing or unexpected body files.")
    actual_root_paths = {entry.name for entry in bundle_path.iterdir()}
    if actual_root_paths != {MANIFEST_FILE_NAME, "bodies"}:
        raise SourceBundleError("Bundle contains unexpected files.")
    manifest_without_digest = {key: value for key, value in manifest.items() if key != "bundle_sha256"}
    digest = _bundle_digest(manifest_without_digest)
    if manifest["bundle_sha256"] != digest or (expected_digest is not None and expected_digest != digest):
        raise SourceBundleError("Bundle digest does not match expected immutable payload.")
    return SourceBundle(path=bundle_path, manifest=manifest, bodies=bodies)
