"""Internal full-text retrieval abstraction.

This module normalizes best-available content for a single PMID while keeping
provider functions injectable for deterministic unit tests.
"""

from __future__ import annotations

import inspect
import json
import os
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Awaitable, Literal
from urllib.parse import quote

FullTextTier = Literal[
    "pmc_fulltext",
    "structured_abstract",
    "plain_abstract",
    "local_fulltext",
    "missing",
]
Provider = Callable[[str], Any | Awaitable[Any]]

_FULLTEXT_DB_ENV_VAR = "CASEPREP_FULLTEXT_DB"
_DEFAULT_FULLTEXT_DB = Path(
    "/mnt/c/dev/NSGY_DB_lean/fulltext/neurointerventional_fulltext.sqlite"
)

_SECTION_KEYS = ("label", "heading", "title", "name")
_TEXT_KEYS = ("text", "content", "body", "value")
_KNOWN_CONTENT_KEYS = {
    "abstract",
    "body",
    "content",
    "doi",
    "full_text",
    "fulltext",
    "metadata",
    "pmcid",
    "sections",
    "source",
    "text",
    "tier",
    "title",
    "warnings",
}


@dataclass(frozen=True)
class FullTextRecord:
    """Normalized best-available full-text content for one PMID.

    This is the Phase 4 Task 4.1 plan shape.  ``source`` and ``abstract`` are
    retained as read-only compatibility aliases for older callers, but the
    primary public API is ``tier``/``text``/``sections``/``metadata``.
    """

    pmid: str
    tier: FullTextTier | str
    text: str
    sections: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def source(self) -> str:
        """Backward-compatible alias for :attr:`tier`."""
        return self.tier

    @property
    def abstract(self) -> str:
        """Backward-compatible plain-abstract alias.

        Older code used ``abstract`` for the text returned by the plain abstract
        provider.  For non-plain tiers there is no separate abstract field in
        the plan API, so return an empty string unless an explicit abstract was
        placed in metadata by a provider.
        """
        if self.tier == "plain_abstract":
            return self.text
        raw = self.metadata.get("abstract")
        return raw if isinstance(raw, str) else ""

    @property
    def title(self) -> str:
        """Backward-compatible title accessor stored in metadata."""
        raw = self.metadata.get("title")
        return raw if isinstance(raw, str) else ""

    @property
    def pmcid(self) -> str | None:
        """Backward-compatible PMCID accessor stored in metadata."""
        raw = self.metadata.get("pmcid")
        return raw if isinstance(raw, str) else None

    @property
    def doi(self) -> str | None:
        """Backward-compatible DOI accessor stored in metadata."""
        raw = self.metadata.get("doi")
        return raw if isinstance(raw, str) else None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation using plan fields."""
        return _json_safe({
            "pmid": self.pmid,
            "tier": self.tier,
            "text": self.text,
            "sections": self.sections,
            "metadata": self.metadata,
            "warnings": self.warnings,
        })


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _default_pmc_fulltext_provider(pmid: str) -> dict[str, Any]:
    from caseprep.mcp_server import _pubmed_fulltext

    return await _maybe_await(_pubmed_fulltext([pmid]))


async def _default_structured_abstract_provider(pmid: str) -> dict[str, Any]:
    from caseprep.mcp_server import _pubmed_structured_abstracts

    return await _maybe_await(_pubmed_structured_abstracts([pmid]))


async def _default_plain_abstract_provider(pmid: str) -> dict[str, Any]:
    from caseprep.mcp_server import _pubmed_abstracts

    return await _maybe_await(_pubmed_abstracts([pmid]))



class FullTextRetriever:
    """Retrieve best available single-PMID content using injectable providers."""

    def __init__(
        self,
        *,
        pmc_fulltext_provider: Provider | None = None,
        structured_abstract_provider: Provider | None = None,
        plain_abstract_provider: Provider | None = None,
        local_fulltext_provider: Provider | None = None,
        fulltext_db: str | Path | None = None,
    ) -> None:
        env_fulltext_db = os.environ.get(_FULLTEXT_DB_ENV_VAR)
        self._fulltext_db = Path(
            fulltext_db if fulltext_db is not None else env_fulltext_db or _DEFAULT_FULLTEXT_DB
        )
        explicit_fulltext_db = fulltext_db is not None or bool(env_fulltext_db)
        self._local_fulltext_preflight_warnings: tuple[str, ...] = ()
        if local_fulltext_provider is None and explicit_fulltext_db and not self._fulltext_db.exists():
            self._local_fulltext_preflight_warnings = (
                _missing_local_db_warning(self._fulltext_db),
            )

        self._pmc_fulltext_provider = (
            pmc_fulltext_provider or _default_pmc_fulltext_provider
        )
        self._structured_abstract_provider = (
            structured_abstract_provider or _default_structured_abstract_provider
        )
        self._plain_abstract_provider = (
            plain_abstract_provider or _default_plain_abstract_provider
        )
        self._local_fulltext_provider = (
            local_fulltext_provider or self._fetch_local_fulltext
        )

    async def retrieve(self, pmid: str) -> FullTextRecord:
        """Return PMC full text, structured abstract, plain abstract, local, or missing."""
        normalized_pmid = str(pmid)
        warnings: list[str] = []

        for tier, provider, normalizer in (
            ("pmc_fulltext", self._pmc_fulltext_provider, _normalize_pmc_fulltext),
            (
                "structured_abstract",
                self._structured_abstract_provider,
                _normalize_structured_abstract,
            ),
            ("plain_abstract", self._plain_abstract_provider, _normalize_plain_abstract),
            ("local_fulltext", self._local_fulltext_provider, _normalize_local_fulltext),
        ):
            try:
                raw_result = await _maybe_await(provider(normalized_pmid))
            except Exception as exc:  # pragma: no cover - exact branch covered by tests
                warnings.append(f"{tier} provider failed: {type(exc).__name__}: {exc}")
                if tier == "plain_abstract":
                    _extend_unique(warnings, self._local_fulltext_preflight_warnings)
                continue

            record = normalizer(normalized_pmid, raw_result)
            if record is not None:
                preflight_warnings = (
                    self._local_fulltext_preflight_warnings
                    if tier == "plain_abstract"
                    else ()
                )
                return replace(record, warnings=(*warnings, *preflight_warnings, *record.warnings))
            warnings.extend(
                warning
                for warning in _provider_warnings(normalized_pmid, raw_result)
                if warning not in warnings
            )
            if tier == "plain_abstract":
                _extend_unique(warnings, self._local_fulltext_preflight_warnings)

        return FullTextRecord(
            pmid=normalized_pmid,
            tier="missing",
            text="",
            warnings=(*warnings, "No full text or abstract available for PMID",),
        )

    def _fetch_local_fulltext(self, pmid: str) -> dict[str, Any] | None:
        """Fetch one PMID from the optional local SQLite fulltext database.

        Two local schemas are supported:

        * the small test/development fixture schema
          ``fulltext_records(pmid, title, text, sections_json, pmcid, doi)``;
        * the real NSGY fulltext DB schema
          ``works`` + ``identifiers`` + ``text_passages``.

        The DB is opened read-only via SQLite URI mode and closed on every call.
        Missing DBs or schema mismatches return warning payloads rather than
        raising, allowing PubMed/PMC fallback semantics to continue.
        """
        db_path = self._fulltext_db
        if not db_path.exists():
            warning = _missing_local_db_warning(db_path)
            if warning in self._local_fulltext_preflight_warnings:
                return None
            return {"warnings": (warning,)}

        try:
            with closing(sqlite3.connect(_sqlite_readonly_uri(db_path), uri=True)) as conn:
                conn.row_factory = sqlite3.Row
                payload = self._query_local_fulltext(conn, pmid, db_path)
        except sqlite3.OperationalError as exc:
            return {"warnings": (f"local fulltext DB schema mismatch: {exc}",)}
        except sqlite3.Error as exc:
            return {"warnings": (f"local fulltext DB lookup failed: {exc}",)}

        return payload

    def _query_local_fulltext(
        self,
        conn: sqlite3.Connection,
        pmid: str,
        db_path: Path,
    ) -> dict[str, Any] | None:
        """Run local fulltext lookup against supported SQLite schemas."""
        schema_errors: list[str] = []
        artificial_schema_seen = False
        real_schema_seen = False

        try:
            row = conn.execute(
                """
                SELECT pmid, title, text, sections_json, pmcid, doi
                FROM fulltext_records
                WHERE pmid = ?
                LIMIT 1
                """,
                (pmid,),
            ).fetchone()
            artificial_schema_seen = True
            if row is not None:
                return _payload_from_fulltext_records_row(row)
        except sqlite3.OperationalError as exc:
            schema_errors.append(f"fulltext_records schema unavailable: {exc}")

        try:
            payload, real_schema_seen = _query_nsgy_fulltext_schema(conn, pmid, db_path)
            if payload is not None:
                return payload
        except sqlite3.OperationalError as exc:
            schema_errors.append(f"works/identifiers/text_passages schema unavailable: {exc}")

        if not artificial_schema_seen and not real_schema_seen:
            detail = "; ".join(schema_errors) or (
                "expected either fulltext_records or works/identifiers/text_passages tables"
            )
            return {"warnings": (f"local fulltext DB schema mismatch: {detail}",)}

        return None


_PMID_SCHEME_NAMES = ("pmid", "pubmed", "pubmed_id", "pubmed id", "pubmedid")
_DOI_SCHEME_NAMES = ("doi", "digital_object_identifier", "digital object identifier")
_PMCID_SCHEME_NAMES = ("pmcid", "pmc", "pmc_id", "pmc id")


def _payload_from_fulltext_records_row(row: Mapping[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    sections = _decode_local_sections(_row_get(row, "sections_json"), warnings)
    payload: dict[str, Any] = {
        "title": _row_get(row, "title"),
        "text": _row_get(row, "text"),
        "sections": sections,
        "pmcid": _row_get(row, "pmcid"),
        "doi": _row_get(row, "doi"),
        "source": "local_fulltext_db",
    }
    if warnings:
        payload["warnings"] = tuple(warnings)
    return payload


def _query_nsgy_fulltext_schema(
    conn: sqlite3.Connection,
    pmid: str,
    db_path: Path,
) -> tuple[dict[str, Any] | None, bool]:
    """Lookup PMID in the real NSGY fulltext schema.

    Returns ``(payload, schema_seen)``. ``schema_seen`` is true once the core
    ``works`` and ``text_passages`` tables are present, even if the PMID is not
    found, so missing content can fall through silently while true schema
    mismatches produce a warning.
    """
    works_cols = _table_columns(conn, "works")
    passage_cols = _table_columns(conn, "text_passages")
    missing_tables = [
        table
        for table, columns in (("works", works_cols), ("text_passages", passage_cols))
        if not columns
    ]
    if missing_tables:
        raise sqlite3.OperationalError(
            f"missing required table(s): {', '.join(missing_tables)}"
        )
    if "id" not in works_cols:
        raise sqlite3.OperationalError("works table is missing required id column")
    if "work_id" not in passage_cols:
        raise sqlite3.OperationalError("text_passages table is missing required work_id column")

    work_id = _resolve_nsgy_work_id(conn, pmid, works_cols)
    if not work_id:
        return None, True

    work_row = conn.execute(
        "SELECT * FROM works WHERE id = ? LIMIT 1",
        (work_id,),
    ).fetchone()
    sections = _nsgy_text_passage_sections(conn, work_id, passage_cols)
    metadata: dict[str, Any] = {
        "work_id": work_id,
        "source_path": str(db_path),
        "schema": "works/identifiers/text_passages",
    }

    title = _optional_str(_row_get(work_row, "title")) if work_row is not None else None
    abstract = _optional_str(_row_get(work_row, "abstract")) if work_row is not None else None
    if abstract:
        metadata["abstract"] = abstract
        if not sections:
            sections = {"ABSTRACT": abstract}

    for column, metadata_key in (
        ("pub_year", "year"),
        ("journal_title", "journal"),
        ("primary_domain", "primary_domain"),
        ("study_design", "study_design"),
        ("evidence_tier", "evidence_tier"),
    ):
        value = _row_get(work_row, column) if work_row is not None else None
        if value is not None and value != "":
            metadata[metadata_key] = value

    doi = _identifier_value(conn, work_id, _DOI_SCHEME_NAMES)
    pmcid = _identifier_value(conn, work_id, _PMCID_SCHEME_NAMES)
    if not sections:
        return None, True

    payload: dict[str, Any] = {
        "sections": sections,
        "metadata": metadata,
        "source": "local_fulltext_db",
    }
    if title:
        payload["title"] = title
    if doi:
        payload["doi"] = doi
    if pmcid:
        payload["pmcid"] = pmcid
    return payload, True


def _resolve_nsgy_work_id(
    conn: sqlite3.Connection,
    pmid: str,
    works_cols: set[str],
) -> str | None:
    id_cols = _table_columns(conn, "identifiers")
    if {"work_id", "value"}.issubset(id_cols):
        indicator_conditions = _identifier_indicator_conditions(id_cols, _PMID_SCHEME_NAMES)
        if indicator_conditions:
            row = conn.execute(
                f"""
                SELECT work_id FROM identifiers
                WHERE CAST(value AS TEXT) = ? AND ({indicator_conditions})
                LIMIT 1
                """,
                (pmid,),
            ).fetchone()
            work_id = _optional_str(_row_get(row, "work_id")) if row is not None else None
            if work_id:
                return work_id

    for column in ("pmid", "pubmed_id", "pubmedid"):
        if column in works_cols:
            row = conn.execute(
                f"SELECT id FROM works WHERE CAST({column} AS TEXT) = ? LIMIT 1",
                (pmid,),
            ).fetchone()
            work_id = _optional_str(_row_get(row, "id")) if row is not None else None
            if work_id:
                return work_id
    return None


def _nsgy_text_passage_sections(
    conn: sqlite3.Connection,
    work_id: str,
    passage_cols: set[str],
) -> dict[str, str]:
    text_col = next((col for col in ("content", "text", "body", "value") if col in passage_cols), None)
    if text_col is None:
        raise sqlite3.OperationalError(
            "text_passages table is missing a content/text/body/value column"
        )
    section_col = next(
        (
            col
            for col in ("section_type", "section", "label", "heading", "title", "name")
            if col in passage_cols
        ),
        None,
    )
    order_cols = [
        col
        for col in ("sequence_number", "position", "passage_index", "sort_order", "id")
        if col in passage_cols
    ]
    order_clause = f" ORDER BY {', '.join(order_cols)}" if order_cols else ""
    label_expr = section_col if section_col is not None else "NULL"
    rows = conn.execute(
        f"""
        SELECT {label_expr} AS section_label, {text_col} AS content
        FROM text_passages
        WHERE work_id = ?{order_clause}
        """,
        (work_id,),
    ).fetchall()

    grouped: dict[str, list[str]] = {}
    for row in rows:
        content = _optional_str(_row_get(row, "content"))
        if not content:
            continue
        label = _optional_str(_row_get(row, "section_label")) or "FULL_TEXT"
        grouped.setdefault(label, []).append(content)
    return {label: "\n\n".join(parts) for label, parts in grouped.items()}


def _identifier_value(
    conn: sqlite3.Connection,
    work_id: str,
    scheme_names: tuple[str, ...],
) -> str | None:
    id_cols = _table_columns(conn, "identifiers")
    if not {"work_id", "value"}.issubset(id_cols):
        return None
    indicator_conditions = _identifier_indicator_conditions(id_cols, scheme_names)
    if not indicator_conditions:
        return None
    row = conn.execute(
        f"""
        SELECT value FROM identifiers
        WHERE work_id = ? AND ({indicator_conditions})
        LIMIT 1
        """,
        (work_id,),
    ).fetchone()
    return _optional_str(_row_get(row, "value")) if row is not None else None


def _identifier_indicator_conditions(
    id_cols: set[str],
    scheme_names: tuple[str, ...],
) -> str:
    quoted_values = ", ".join(f"'{name}'" for name in scheme_names)
    return " OR ".join(
        f"lower({column}) IN ({quoted_values})"
        for column in ("scheme", "name")
        if column in id_cols
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _row_get(row: Any, key: str) -> Any:
    if row is None:
        return None
    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return None


def _normalize_pmc_fulltext(pmid: str, raw: Any) -> FullTextRecord | None:
    result = _unwrap_pmid_result(pmid, raw)
    if _is_empty(result):
        return None

    if isinstance(result, str):
        text = result.strip()
        if not text:
            return None
        sections = {"FULL_TEXT": text}
        return FullTextRecord(
            pmid=pmid,
            tier="pmc_fulltext",
            text=text,
            sections=sections,
        )

    if not isinstance(result, Mapping):
        return None

    sections = _normalize_sections(result.get("sections"))
    if not sections:
        text = _first_text(result, ("full_text", "fulltext", "text", "body", "content"))
        if text:
            sections = {"FULL_TEXT": text}
    if not sections:
        return None

    metadata = _metadata(result)
    abstract = _optional_str(result.get("abstract"))
    if abstract:
        metadata.setdefault("abstract", abstract)

    return FullTextRecord(
        pmid=pmid,
        tier="pmc_fulltext",
        text=_text_from_sections(sections),
        sections=sections,
        metadata=metadata,
        warnings=_warnings(result),
    )


def _normalize_structured_abstract(pmid: str, raw: Any) -> FullTextRecord | None:
    result = _unwrap_pmid_result(pmid, raw)
    if _is_empty(result):
        return None

    if isinstance(result, str):
        sections = _normalize_sections({"TEXT": result})
        metadata: dict[str, Any] = {}
        warnings: tuple[str, ...] = ()
    elif isinstance(result, Mapping):
        sections = _normalize_sections(result.get("sections"))
        if not sections:
            sections = _normalize_sections({
                key: value
                for key, value in result.items()
                if _is_structured_abstract_section_key(key)
            })
        metadata = _metadata(result)
        warnings = _warnings(result)
    else:
        return None

    if not sections:
        return None
    return FullTextRecord(
        pmid=pmid,
        tier="structured_abstract",
        text=_text_from_sections(sections),
        sections=sections,
        metadata=metadata,
        warnings=warnings,
    )


def _is_structured_abstract_section_key(key: Any) -> bool:
    """Return True for top-level structured abstract section labels.

    ``TEXT`` is emitted by the PubMed structured abstract provider for
    unlabeled abstract paragraphs. Treat that exact key as structured content
    rather than dropping it as the generic ``text`` content/metadata key.
    """
    key_text = str(key)
    return key_text == "TEXT" or key_text.lower() not in _KNOWN_CONTENT_KEYS


def _normalize_plain_abstract(pmid: str, raw: Any) -> FullTextRecord | None:
    result = _unwrap_pmid_result(pmid, raw)
    if _is_empty(result):
        return None

    metadata: dict[str, Any] = {}
    warnings: tuple[str, ...] = ()
    if isinstance(result, str):
        text = result.strip()
    elif isinstance(result, Mapping):
        text = _first_text(result, ("abstract", "text", "content", "body"))
        metadata = _metadata(result)
        warnings = _warnings(result)
    else:
        return None

    if not text:
        return None
    return FullTextRecord(
        pmid=pmid,
        tier="plain_abstract",
        text=text,
        sections={},
        metadata=metadata,
        warnings=warnings,
    )


def _normalize_local_fulltext(pmid: str, raw: Any) -> FullTextRecord | None:
    result = _unwrap_pmid_result(pmid, raw)
    if _is_empty(result):
        return None

    if isinstance(result, str):
        text = result.strip()
        if not text:
            return None
        return FullTextRecord(
            pmid=pmid,
            tier="local_fulltext",
            text=text,
            sections={"FULL_TEXT": text},
        )

    if not isinstance(result, Mapping):
        return None

    sections = _normalize_sections(result.get("sections"))
    if not sections:
        text = _first_text(result, ("full_text", "fulltext", "text", "body", "content"))
        if text:
            sections = {"FULL_TEXT": text}
    if not sections:
        return None

    return FullTextRecord(
        pmid=pmid,
        tier="local_fulltext",
        text=_text_from_sections(sections),
        sections=sections,
        metadata=_metadata(result),
        warnings=_warnings(result),
    )


def _missing_local_db_warning(db_path: Path) -> str:
    return f"local fulltext DB path does not exist: {db_path}"


def _sqlite_readonly_uri(db_path: Path) -> str:
    """Return a SQLite URI that opens an existing DB in read-only mode."""
    return f"file:{quote(db_path.resolve(strict=False).as_posix(), safe='/')}?mode=ro"


def _decode_local_sections(raw: Any, warnings: list[str]) -> Any:
    if _is_empty(raw):
        return {}
    try:
        decoded = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        warnings.append(f"local fulltext DB sections_json could not be parsed: {exc}")
        return {}
    if isinstance(decoded, Mapping | list):
        return decoded
    warnings.append("local fulltext DB sections_json did not contain an object or list")
    return {}


def _provider_warnings(pmid: str, raw: Any) -> tuple[str, ...]:
    result = _unwrap_pmid_result(pmid, raw)
    if isinstance(result, Mapping):
        return _warnings(result)
    return ()


def _extend_unique(target: list[str], values: tuple[str, ...]) -> None:
    target.extend(value for value in values if value not in target)


def _unwrap_pmid_result(pmid: str, raw: Any) -> Any:
    """Accept either single-record or batch dicts keyed by PMID.

    A batch dictionary that does not include the requested PMID is treated as no
    content, so retrieval falls through to the next provider instead of treating
    some other PMID's payload as this PMID's content.
    """
    if not isinstance(raw, Mapping):
        return raw

    matching_key = next((key for key in raw if str(key) == pmid), None)
    if matching_key is not None:
        lower_keys = {str(key).lower() for key in raw}
        if lower_keys & _KNOWN_CONTENT_KEYS:
            return raw
        return raw[matching_key]

    if _looks_like_pmid_batch(raw):
        return None

    return raw


def _looks_like_pmid_batch(raw: Mapping[Any, Any]) -> bool:
    """Return True for dicts that appear to be batch results keyed by PMID."""
    keys = list(raw.keys())
    return bool(keys) and any(_is_pmid_like_key(key) for key in keys)


def _is_pmid_like_key(key: Any) -> bool:
    text = str(key).strip()
    return text.isdigit()


def _normalize_sections(raw: Any) -> dict[str, str]:
    if _is_empty(raw):
        return {}

    sections: dict[str, str] = {}
    if isinstance(raw, Mapping):
        iterable = [
            {"label": str(label), "text": text}
            for label, text in raw.items()
            if not _is_empty(text)
        ]
    elif isinstance(raw, list):
        iterable = raw
    else:
        return {}

    for index, item in enumerate(iterable, start=1):
        if isinstance(item, Mapping):
            label = _first_text(item, _SECTION_KEYS)
            text = _first_text(item, _TEXT_KEYS)
            if not label and "label" in item:
                label = _optional_str(item.get("label")) or ""
            if text:
                sections[_unique_section_label(sections, label or f"SECTION_{index}")] = text
        elif isinstance(item, str) and item.strip():
            sections[_unique_section_label(sections, f"SECTION_{index}")] = item.strip()
    return sections


def _unique_section_label(sections: Mapping[str, str], label: str) -> str:
    if label not in sections:
        return label
    index = 2
    while f"{label}_{index}" in sections:
        index += 1
    return f"{label}_{index}"


def _text_from_sections(sections: Mapping[str, str]) -> str:
    return "\n\n".join(text for text in sections.values() if text)


def _first_text(value: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        raw = value.get(key)
        text = _optional_str(raw)
        if text:
            return text
    return ""


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    raw_metadata = value.get("metadata")
    metadata: dict[str, Any]
    if isinstance(raw_metadata, Mapping):
        metadata = dict(raw_metadata)
    else:
        metadata = {}

    for key in ("title", "pmcid", "doi", "source"):
        text = _optional_str(value.get(key))
        if text:
            metadata.setdefault(key, text)
    return metadata


def _warnings(value: Mapping[str, Any]) -> tuple[str, ...]:
    raw_warnings = value.get("warnings")
    if raw_warnings is None:
        return ()
    if isinstance(raw_warnings, str):
        return (raw_warnings,)
    if isinstance(raw_warnings, list | tuple):
        return tuple(str(warning) for warning in raw_warnings)
    return (str(raw_warnings),)


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == {} or value == []


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(child) for child in value]
    return str(value)


__all__ = ["FullTextRecord", "FullTextRetriever"]
