"""Expand weblist ``sources`` rows into one concrete fetch target per company or career URL."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml


def _registry_dir() -> Path:
    return Path(__file__).resolve().parent / "registries"


def _resolve_registry_reference(reference: str, *, weblist_parent: Path) -> Path:
    """
    Resolve a registry file path.

    * ``package:filename.yaml`` — bundled under ``job_hunter/job_listings/registries/``.
    * Absolute filesystem paths — used as-is.
    * Any other string — treated as relative to the weblist YAML parent directory.
    """
    trimmed = reference.strip()
    if trimmed.startswith("package:"):
        name = trimmed[len("package:") :].lstrip("/")
        if not name or ".." in name or name.startswith("/"):
            raise ValueError(f"Invalid package registry reference: {reference!r}")
        return (_registry_dir() / name).resolve()
    candidate = Path(trimmed)
    if candidate.is_absolute():
        return candidate.resolve()
    return (weblist_parent / candidate).resolve()


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Registry file not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Registry root must be a mapping: {path}")
    return payload


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _child_id(parent_id: str, token: str) -> str:
    safe = "".join(character if character.isalnum() or character in ("-", "_") else "_" for character in token)
    return f"{parent_id}__{safe}"


def _enabled_flag(source: Mapping[str, Any]) -> bool:
    return source.get("enabled") is not False


def _merge_greenhouse_tokens(source: Mapping[str, Any], *, weblist_parent: Path) -> list[str]:
    tokens: list[str] = []
    single = source.get("board_token")
    if isinstance(single, str) and single.strip():
        tokens.append(single.strip())
    many = source.get("board_tokens")
    if many is not None:
        if not isinstance(many, list):
            raise ValueError("board_tokens must be a list of strings when present")
        tokens.extend(str(item).strip() for item in many if str(item).strip())
    registry_ref = source.get("board_tokens_registry")
    if registry_ref is not None:
        if not isinstance(registry_ref, str) or not registry_ref.strip():
            raise ValueError("board_tokens_registry must be a non-empty string when present")
        registry_path = _resolve_registry_reference(registry_ref, weblist_parent=weblist_parent)
        document = _load_yaml_mapping(registry_path)
        from_file = document.get("board_tokens")
        if not isinstance(from_file, list):
            raise ValueError(f"Registry {registry_path} must define board_tokens: as a list")
        tokens.extend(str(item).strip() for item in from_file if str(item).strip())
    return _dedupe_preserve_order(tokens)


def _merge_ashby_slugs(source: Mapping[str, Any], *, weblist_parent: Path) -> list[str]:
    slugs: list[str] = []
    single = source.get("organization_slug")
    if isinstance(single, str) and single.strip():
        slugs.append(single.strip())
    many = source.get("organization_slugs")
    if many is not None:
        if not isinstance(many, list):
            raise ValueError("organization_slugs must be a list of strings when present")
        slugs.extend(str(item).strip() for item in many if str(item).strip())
    registry_ref = source.get("organization_slugs_registry")
    if registry_ref is not None:
        if not isinstance(registry_ref, str) or not registry_ref.strip():
            raise ValueError("organization_slugs_registry must be a non-empty string when present")
        registry_path = _resolve_registry_reference(registry_ref, weblist_parent=weblist_parent)
        document = _load_yaml_mapping(registry_path)
        from_file = document.get("organization_slugs")
        if not isinstance(from_file, list):
            raise ValueError(f"Registry {registry_path} must define organization_slugs: as a list")
        slugs.extend(str(item).strip() for item in from_file if str(item).strip())
    return _dedupe_preserve_order(slugs)


def _merge_workable_slugs(source: Mapping[str, Any], *, weblist_parent: Path) -> list[str]:
    slugs: list[str] = []
    single = source.get("apply_account_slug")
    if isinstance(single, str) and single.strip():
        slugs.append(single.strip())
    many = source.get("apply_account_slugs")
    if many is not None:
        if not isinstance(many, list):
            raise ValueError("apply_account_slugs must be a list of strings when present")
        slugs.extend(str(item).strip() for item in many if str(item).strip())
    registry_ref = source.get("apply_account_slugs_registry")
    if registry_ref is not None:
        if not isinstance(registry_ref, str) or not registry_ref.strip():
            raise ValueError("apply_account_slugs_registry must be a non-empty string when present")
        registry_path = _resolve_registry_reference(registry_ref, weblist_parent=weblist_parent)
        document = _load_yaml_mapping(registry_path)
        from_file = document.get("apply_account_slugs")
        if not isinstance(from_file, list):
            raise ValueError(f"Registry {registry_path} must define apply_account_slugs: as a list")
        slugs.extend(str(item).strip() for item in from_file if str(item).strip())
    return _dedupe_preserve_order(slugs)


def _merge_custom_pages(source: Mapping[str, Any], *, weblist_parent: Path) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    single_url = source.get("careers_page_url")
    if isinstance(single_url, str) and single_url.strip():
        display = source.get("display_name")
        pages.append(
            {
                "url": single_url.strip(),
                "display_name": str(display).strip() if isinstance(display, str) and display.strip() else "",
            }
        )
    many = source.get("careers_pages")
    if many is not None:
        if not isinstance(many, list):
            raise ValueError("careers_pages must be a list of mappings when present")
        for index, item in enumerate(many):
            if not isinstance(item, dict):
                raise ValueError(f"careers_pages[{index}] must be a mapping")
            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                raise ValueError(f"careers_pages[{index}] needs a non-empty url string")
            display_name = item.get("display_name")
            pages.append(
                {
                    "url": url.strip(),
                    "display_name": str(display_name).strip()
                    if isinstance(display_name, str) and display_name.strip()
                    else "",
                }
            )
    registry_ref = source.get("careers_pages_registry")
    if registry_ref is not None:
        if not isinstance(registry_ref, str) or not registry_ref.strip():
            raise ValueError("careers_pages_registry must be a non-empty string when present")
        registry_path = _resolve_registry_reference(registry_ref, weblist_parent=weblist_parent)
        document = _load_yaml_mapping(registry_path)
        from_file = document.get("careers_pages")
        if not isinstance(from_file, list):
            raise ValueError(f"Registry {registry_path} must define careers_pages: as a list")
        for index, item in enumerate(from_file):
            if not isinstance(item, dict):
                raise ValueError(f"careers_pages[{index}] in {registry_path} must be a mapping")
            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                raise ValueError(f"careers_pages[{index}] in {registry_path} needs url")
            display_name = item.get("display_name")
            pages.append(
                {
                    "url": url.strip(),
                    "display_name": str(display_name).strip()
                    if isinstance(display_name, str) and display_name.strip()
                    else "",
                }
            )
    # De-dupe custom URLs while preserving order
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for page in pages:
        url = page["url"]
        if url in seen:
            continue
        seen.add(url)
        unique.append(page)
    return unique


def expand_weblist_sources(sources: list[dict[str, Any]], *, weblist_path: Path) -> list[dict[str, Any]]:
    """
    Expand multi-company weblist rows into one row per board slug / token / career URL.

    Single-value keys (``board_token``, ``organization_slug``, …) continue to work.
    """
    weblist_parent = weblist_path.expanduser().resolve().parent
    expanded: list[dict[str, Any]] = []
    for source in sources:
        parent_id = str(source.get("id", "")).strip()
        if not parent_id:
            raise ValueError("Each weblist source must include a non-empty 'id' string")
        kind = source.get("kind")
        if not _enabled_flag(source):
            expanded.append(dict(source))
            continue
        if kind == "greenhouse":
            tokens = _merge_greenhouse_tokens(source, weblist_parent=weblist_parent)
            if not tokens:
                raise ValueError(
                    f"greenhouse source {parent_id!r} needs at least one of: "
                    "board_token, board_tokens, board_tokens_registry",
                )
            for token in tokens:
                child_id = parent_id if len(tokens) == 1 else _child_id(parent_id, token)
                row: dict[str, Any] = {
                    "id": child_id,
                    "kind": "greenhouse",
                    "board_token": token,
                    "enabled": True,
                }
                if len(tokens) > 1:
                    row["expansion_parent_id"] = parent_id
                expanded.append(row)
            continue
        if kind == "ashby":
            slugs = _merge_ashby_slugs(source, weblist_parent=weblist_parent)
            if not slugs:
                raise ValueError(
                    f"ashby source {parent_id!r} needs at least one of: "
                    "organization_slug, organization_slugs, organization_slugs_registry",
                )
            for slug in slugs:
                child_id = parent_id if len(slugs) == 1 else _child_id(parent_id, slug)
                row = {
                    "id": child_id,
                    "kind": "ashby",
                    "organization_slug": slug,
                    "enabled": True,
                }
                if len(slugs) > 1:
                    row["expansion_parent_id"] = parent_id
                expanded.append(row)
            continue
        if kind == "workable":
            slugs = _merge_workable_slugs(source, weblist_parent=weblist_parent)
            if not slugs:
                raise ValueError(
                    f"workable source {parent_id!r} needs at least one of: "
                    "apply_account_slug, apply_account_slugs, apply_account_slugs_registry",
                )
            for slug in slugs:
                child_id = parent_id if len(slugs) == 1 else _child_id(parent_id, slug)
                row = {
                    "id": child_id,
                    "kind": "workable",
                    "apply_account_slug": slug,
                    "enabled": True,
                }
                if len(slugs) > 1:
                    row["expansion_parent_id"] = parent_id
                expanded.append(row)
            continue
        if kind == "custom_career_page":
            pages = _merge_custom_pages(source, weblist_parent=weblist_parent)
            if not pages:
                raise ValueError(
                    f"custom_career_page source {parent_id!r} needs at least one of: "
                    "careers_page_url, careers_pages, careers_pages_registry",
                )
            for index, page in enumerate(pages):
                child_id = parent_id if len(pages) == 1 else f"{parent_id}__{index}"
                row = {
                    "id": child_id,
                    "kind": "custom_career_page",
                    "display_name": page["display_name"] or f"{parent_id}_{index}",
                    "careers_page_url": page["url"],
                    "enabled": True,
                }
                if len(pages) > 1:
                    row["expansion_parent_id"] = parent_id
                expanded.append(row)
            continue
        raise ValueError(f"Unsupported weblist source kind {kind!r} for source id {parent_id!r}")
    return expanded
