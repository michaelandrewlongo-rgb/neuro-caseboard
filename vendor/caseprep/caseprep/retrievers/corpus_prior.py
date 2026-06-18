"""SQLite-backed neurosurgery corpus prior adapter seam.

Phase 2 keeps the local corpus strictly as a retrieval prior: parser-derived
``CaseSpec`` facts remain canonical, and corpus access must fail closed with
warnings rather than exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
import sqlite3
from os import PathLike
from pathlib import Path
from typing import Iterable

from caseprep.case_parser import CaseSpec
from caseprep.profile_classifier import ProfileName
from caseprep.procedure_taxonomy import ProcedureFamily
from caseprep.query_enrichment import ConceptType, ExpansionProvenance, ExpansionTerm, PriorEnrichment, SeedSource

_DEFAULT_CORPUS_DB = Path("/mnt/c/dev/NSGY_DB_lean/corpus/neurointerventional.sqlite")
_REQUIRED_TABLES = frozenset(
    {
        "works",
        "subdomain_assignments",
        "identifiers",
        "subjects",
        "work_subjects",
    }
)
_OFF_TARGET_CITATION_FLOOR = 1000
_SEED_CITATION_FLOOR = 1000
_CANDIDATE_ROW_LIMIT = 250
_OFF_TARGET_ROW_LIMIT = 100
_MAX_PROVENANCE_PER_TERM = 8
_SEED_TIER_PRIORITIES = {
    "guideline": 0,
    "meta_analysis": 1,
    "meta analysis": 1,
    "rct": 2,
    "randomized controlled trial": 2,
    "randomised controlled trial": 2,
    "high": 3,
}
_THROMBECTOMY_CUE_RE = re.compile(
    r"\b(?:thrombectomy|large\s+vessel\s+occlusion|lvo|stroke|mca\s+occlusion|endovascular_thrombectomy)\b",
    re.I,
)
_M1_SEGMENT_CUE_RE = re.compile(r"\bm1\b", re.I)
_M1_OCCLUSION_CUE_RE = re.compile(
    r"(?:\bm1\b(?:[\s/-]+\w+){0,5}[\s/-]+occlus(?:ion|ions|ive|ed)\b|"
    r"\bocclus(?:ion|ions|ive|ed)\b(?:[\s/-]+\w+){0,5}[\s/-]+m1\b)",
    re.I,
)
_OCCLUSION_PATHOLOGY_RE = re.compile(
    r"\b(?:occlus(?:ion|ions|ive|ed)|thrombus|thrombi|thromboembol\w*|embolus|emboli|clot|lvo)\b",
    re.I,
)
_VASCULAR_CONTEXT_RE = re.compile(
    r"\b(?:mca|middle\s+cerebral\s+artery|arter(?:y|ial)|vascular|endovascular|angiograph\w*|ische?mic|ischa?emic|cerebral\s+infarct\w*)\b",
    re.I,
)


@dataclass(frozen=True)
class _CorpusRow:
    work_id: str
    title: str
    abstract: str
    pub_year: int
    evidence_tier: str
    citation_count: int
    subdomain_id: str


@dataclass(frozen=True)
class _CorpusSubject:
    work_id: str
    value: str


@dataclass(frozen=True)
class _CorpusIdentifiers:
    pmid: str | None = None
    doi: str | None = None
    pmcid: str | None = None


@dataclass
class _TermEvidence:
    canonical: str
    aliases: set[str]
    concept_type: ConceptType
    confidence: float
    citation_count: int
    title: str
    provenance: list[ExpansionProvenance] = field(default_factory=list)


@dataclass(frozen=True)
class _KnownTerm:
    canonical: str
    concept_type: ConceptType
    pattern: re.Pattern[str]
    confidence: float


_KNOWN_TERMS: tuple[_KnownTerm, ...] = (
    _KnownTerm("mechanical thrombectomy", "procedure", re.compile(r"\bmechanical\s+thrombectom(?:y|ies)\b", re.I), 0.98),
    _KnownTerm("endovascular thrombectomy", "procedure", re.compile(r"\bendovascular\s+thrombectom(?:y|ies)\b", re.I), 0.97),
    _KnownTerm("thrombectomy", "procedure", re.compile(r"\bthrombectom(?:y|ies)\b", re.I), 0.94),
    _KnownTerm("aspiration thrombectomy", "procedure", re.compile(r"\baspiration(?:\s+thrombectomy)?\b", re.I), 0.88),
    _KnownTerm("coiling", "procedure", re.compile(r"\bcoiling\b", re.I), 0.94),
    _KnownTerm("clipping", "procedure", re.compile(r"\bclipping\b", re.I), 0.94),
    _KnownTerm("stent retriever", "device", re.compile(r"\bstent\s+retriever\b", re.I), 0.94),
    _KnownTerm("flow diverter", "device", re.compile(r"\bflow\s+diverter\b", re.I), 0.92),
    _KnownTerm("flow diversion", "procedure", re.compile(r"\bflow\s+diversion\b", re.I), 0.92),
    _KnownTerm("large vessel occlusion", "pathology", re.compile(r"\b(?:large\s+vessel\s+occlusion|LVO)\b", re.I), 0.96),
    _KnownTerm("M1 occlusion", "anatomy", re.compile(r"\bM1\s+(?:middle\s+cerebral\s+artery\s+)?occlusion\b", re.I), 0.96),
    _KnownTerm("middle cerebral artery occlusion", "anatomy", re.compile(r"\bmiddle\s+cerebral\s+artery\s+occlusion\b", re.I), 0.95),
    _KnownTerm("MCA occlusion", "anatomy", re.compile(r"\bMCA\s+occlusion\b", re.I), 0.95),
    _KnownTerm("MCA aneurysm", "pathology", re.compile(r"\bMCA\s+aneurysm\b", re.I), 0.95),
    _KnownTerm("intracranial aneurysm", "pathology", re.compile(r"\bintracranial\s+aneurysm\b", re.I), 0.94),
    _KnownTerm("aneurysm", "pathology", re.compile(r"\baneurysm\b", re.I), 0.86),
    _KnownTerm("modified Rankin Scale", "outcome", re.compile(r"\b(?:modified\s+Rankin\s+Scale|mRS)\b", re.I), 0.93),
    _KnownTerm("NIHSS", "outcome", re.compile(r"\bNIHSS\b", re.I), 0.91),
    _KnownTerm("TICI", "outcome", re.compile(r"\b(?:m?TICI|thrombolysis\s+in\s+cerebral\s+infarction)\b", re.I), 0.91),
    _KnownTerm("sICH", "outcome", re.compile(r"\b(?:sICH|symptomatic\s+intracranial\s+hemorrhage)\b", re.I), 0.91),
    _KnownTerm("first pass effect", "outcome", re.compile(r"\bfirst\s+pass\s+(?:effect|reperfusion)\b", re.I), 0.86),
)


class NeurosurgeryCorpusPrior:
    """Read-only local SQLite corpus prior adapter.

    The adapter resolves the configured corpus database, opens it in SQLite URI
    read-only mode for each ``enrich`` call, validates the expected schema, and
    returns empty priors plus warnings on availability/schema failure. Corpus
    facts are retrieval hints only and never overwrite parser-derived ``CaseSpec``
    facts.
    """

    def __init__(
        self,
        corpus_db: str | PathLike[str] | None = None,
        *,
        term_limit: int = 24,
        seed_limit: int = 8,
    ) -> None:
        configured_db = corpus_db
        if configured_db is None:
            configured_db = os.environ.get("CASEPREP_CORPUS_DB") or _DEFAULT_CORPUS_DB

        self.db_path = Path(configured_db)
        self.term_limit = max(0, term_limit)
        self.seed_limit = max(0, seed_limit)

    def enrich(
        self,
        case: CaseSpec,
        family: ProcedureFamily | None,
        profile: ProfileName,
    ) -> PriorEnrichment:
        """Return local corpus retrieval priors without mutating parser facts."""

        if not self.db_path.exists():
            warning = f"Local corpus DB missing or unavailable: {self.db_path}"
            return PriorEnrichment(
                warnings=(warning,),
                metadata=self._prior_target_divergence_metadata(warnings=(warning,)),
            )

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(self._readonly_uri(), uri=True)
            missing_tables = self._missing_required_tables(conn)
            if missing_tables:
                warning = (
                    "Local corpus DB schema missing required table(s) "
                    f"{', '.join(sorted(missing_tables))}: {self.db_path}"
                )
                return PriorEnrichment(
                    warnings=(warning,),
                    metadata=self._prior_target_divergence_metadata(warnings=(warning,)),
                )

            available_subdomains = self._available_subdomains(conn)
            candidate_subdomains = self._candidate_subdomains(case, family, profile, available_subdomains)
            if not candidate_subdomains:
                return PriorEnrichment(
                    metadata=self._prior_target_divergence_metadata()
                )

            candidate_rows = self._fetch_rows(conn, candidate_subdomains)
            candidate_subjects = self._fetch_subjects(conn, [row.work_id for row in candidate_rows])
            expansion_terms = self._extract_terms(candidate_rows, candidate_subjects, quarantine=False)
            bounded_terms = self._bound_terms(expansion_terms, self.term_limit)

            seed_rows = self._fetch_seed_rows(conn, candidate_subdomains, self.seed_limit)
            target_rows = self._unique_rows(candidate_rows, seed_rows)
            target_identifiers = self._fetch_identifiers(conn, [row.work_id for row in target_rows])
            seed_sources = self._extract_seed_sources(seed_rows, target_identifiers, self.seed_limit)
            local_corpus_only_records = self._count_local_corpus_only_records(
                target_rows, target_identifiers
            )

            off_target_rows = self._fetch_off_target_rows(conn, candidate_subdomains)
            off_target_subjects = self._fetch_subjects(conn, [row.work_id for row in off_target_rows])
            quarantined_terms = self._extract_terms(off_target_rows, off_target_subjects, quarantine=True)
            bounded_quarantined_terms = self._bound_terms(quarantined_terms, self.term_limit)

            return PriorEnrichment(
                expansion_terms=bounded_terms,
                seed_sources=seed_sources,
                subdomain_hints=tuple(candidate_subdomains),
                quarantined_terms=bounded_quarantined_terms,
                metadata=self._prior_target_divergence_metadata(
                    target_sources=("local_corpus",) if target_rows else (),
                    local_corpus_only_records=local_corpus_only_records,
                    quarantined_count=len(bounded_quarantined_terms),
                ),
            )
        except (OSError, sqlite3.Error) as exc:
            warning = f"Local corpus DB unavailable or unreadable: {self.db_path} ({exc})"
            return PriorEnrichment(
                warnings=(warning,),
                metadata=self._prior_target_divergence_metadata(warnings=(warning,)),
            )
        finally:
            if conn is not None:
                conn.close()

    def _readonly_uri(self) -> str:
        return f"file:{self.db_path}?mode=ro"

    @staticmethod
    def _prior_target_divergence_metadata(
        *,
        target_sources: tuple[str, ...] = (),
        local_corpus_only_records: int = 0,
        quarantined_count: int = 0,
        warnings: tuple[str, ...] = (),
    ) -> dict[str, object]:
        unique_target_sources = tuple(dict.fromkeys(target_sources))
        divergence_warnings = list(warnings)
        if "local_corpus" in unique_target_sources:
            divergence_warnings.append(
                "Local corpus contributes both prior enrichment and target retrieval hints; "
                "treat downstream local_corpus evidence as non-independent and monitor self-bias."
            )
        if quarantined_count:
            divergence_warnings.append(
                f"Quarantined {quarantined_count} off-target local corpus expansion term(s); "
                "quarantined terms are metadata/audit-only and not active retrieval facts."
            )

        return {
            "prior_target_divergence": {
                "prior_sources": ["local_corpus"],
                "target_sources": list(unique_target_sources),
                "local_corpus_only_records": local_corpus_only_records,
                "warnings": divergence_warnings,
                "quarantined_count": quarantined_count,
            }
        }

    @staticmethod
    def _unique_rows(*groups: tuple[_CorpusRow, ...]) -> tuple[_CorpusRow, ...]:
        rows_by_id: dict[str, _CorpusRow] = {}
        for group in groups:
            for row in group:
                rows_by_id.setdefault(row.work_id, row)
        return tuple(rows_by_id.values())

    @staticmethod
    def _count_local_corpus_only_records(
        rows: tuple[_CorpusRow, ...],
        identifiers_by_work_id: dict[str, _CorpusIdentifiers],
    ) -> int:
        count = 0
        for row in rows:
            identifiers = identifiers_by_work_id.get(row.work_id, _CorpusIdentifiers())
            if not (identifiers.pmid or identifiers.doi or identifiers.pmcid):
                count += 1
        return count

    @staticmethod
    def _missing_required_tables(conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        existing_tables = {str(row[0]) for row in rows}
        return set(_REQUIRED_TABLES - existing_tables)

    @staticmethod
    def _available_subdomains(conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute(
            "SELECT DISTINCT subdomain_id FROM subdomain_assignments WHERE subdomain_id IS NOT NULL"
        ).fetchall()
        return {str(row[0]) for row in rows if row[0]}

    @staticmethod
    def _candidate_subdomains(
        case: CaseSpec,
        family: ProcedureFamily | None,
        profile: ProfileName,
        available_subdomains: set[str],
    ) -> tuple[str, ...]:
        text = _case_keyword_blob(case, family, profile)
        candidates: list[str] = []

        if _looks_like_thrombectomy(text):
            candidates.append("stroke_thrombectomy")
        if _looks_like_aneurysm(text):
            candidates.append("aneurysm_sah")

        candidates = [subdomain for subdomain in candidates if subdomain in available_subdomains]

        return tuple(dict.fromkeys(candidates))

    @staticmethod
    def _fetch_rows(conn: sqlite3.Connection, subdomains: tuple[str, ...]) -> tuple[_CorpusRow, ...]:
        if not subdomains:
            return ()
        placeholders = ", ".join("?" for _ in subdomains)
        rows = conn.execute(
            f"""
            SELECT w.id, COALESCE(w.title, ''), COALESCE(w.abstract, ''),
                   COALESCE(w.pub_year, 0), COALESCE(w.evidence_tier, ''),
                   COALESCE(w.citation_count, 0), sa.subdomain_id
            FROM works AS w
            JOIN subdomain_assignments AS sa ON sa.work_id = w.id
            WHERE sa.subdomain_id IN ({placeholders})
            ORDER BY sa.subdomain_id ASC, COALESCE(w.citation_count, 0) DESC, COALESCE(w.title, '') ASC, w.id ASC
            LIMIT ?
            """,
            (*subdomains, _CANDIDATE_ROW_LIMIT),
        ).fetchall()
        return tuple(
            _CorpusRow(
                work_id=str(row[0]),
                title=str(row[1] or ""),
                abstract=str(row[2] or ""),
                pub_year=int(row[3] or 0),
                evidence_tier=str(row[4] or ""),
                citation_count=int(row[5] or 0),
                subdomain_id=str(row[6] or ""),
            )
            for row in rows
        )

    @staticmethod
    def _fetch_off_target_rows(conn: sqlite3.Connection, candidate_subdomains: tuple[str, ...]) -> tuple[_CorpusRow, ...]:
        if not candidate_subdomains:
            return ()
        placeholders = ", ".join("?" for _ in candidate_subdomains)
        rows = conn.execute(
            f"""
            SELECT w.id, COALESCE(w.title, ''), COALESCE(w.abstract, ''),
                   COALESCE(w.pub_year, 0), COALESCE(w.evidence_tier, ''),
                   COALESCE(w.citation_count, 0), sa.subdomain_id
            FROM works AS w
            JOIN subdomain_assignments AS sa ON sa.work_id = w.id
            WHERE sa.subdomain_id NOT IN ({placeholders})
              AND COALESCE(w.citation_count, 0) >= ?
            ORDER BY COALESCE(w.citation_count, 0) DESC, COALESCE(w.title, '') ASC, w.id ASC
            LIMIT ?
            """,
            (*candidate_subdomains, _OFF_TARGET_CITATION_FLOOR, _OFF_TARGET_ROW_LIMIT),
        ).fetchall()
        return tuple(
            _CorpusRow(
                work_id=str(row[0]),
                title=str(row[1] or ""),
                abstract=str(row[2] or ""),
                pub_year=int(row[3] or 0),
                evidence_tier=str(row[4] or ""),
                citation_count=int(row[5] or 0),
                subdomain_id=str(row[6] or ""),
            )
            for row in rows
        )

    @staticmethod
    def _fetch_seed_rows(
        conn: sqlite3.Connection,
        subdomains: tuple[str, ...],
        limit: int,
    ) -> tuple[_CorpusRow, ...]:
        if not subdomains or limit <= 0:
            return ()
        placeholders = ", ".join("?" for _ in subdomains)
        rows = conn.execute(
            f"""
            SELECT w.id, COALESCE(w.title, ''), COALESCE(w.abstract, ''),
                   COALESCE(w.pub_year, 0), COALESCE(w.evidence_tier, ''),
                   COALESCE(w.citation_count, 0), sa.subdomain_id,
                   LOWER(REPLACE(COALESCE(w.evidence_tier, ''), '-', '_')) AS normalized_tier
            FROM works AS w
            JOIN subdomain_assignments AS sa ON sa.work_id = w.id
            WHERE sa.subdomain_id IN ({placeholders})
              AND (
                normalized_tier IN ('guideline', 'meta_analysis', 'rct', 'high')
                OR normalized_tier LIKE '%guideline%'
                OR normalized_tier LIKE '%consensus%'
                OR normalized_tier LIKE '%meta_analysis%'
                OR normalized_tier LIKE '%meta analysis%'
                OR normalized_tier LIKE '%randomized controlled trial%'
                OR normalized_tier LIKE '%randomised controlled trial%'
                OR normalized_tier LIKE '%rct%'
                OR normalized_tier LIKE 'high %'
                OR COALESCE(w.citation_count, 0) >= ?
              )
            ORDER BY
              CASE
                WHEN normalized_tier IN ('guideline')
                  OR normalized_tier LIKE '%guideline%'
                  OR normalized_tier LIKE '%consensus%'
                  THEN 0
                WHEN normalized_tier IN ('meta_analysis')
                  OR normalized_tier LIKE '%meta_analysis%'
                  OR normalized_tier LIKE '%meta analysis%'
                  THEN 1
                WHEN normalized_tier IN ('rct')
                  OR normalized_tier LIKE '%rct%'
                  OR normalized_tier LIKE '%randomized controlled trial%'
                  OR normalized_tier LIKE '%randomised controlled trial%'
                  THEN 2
                WHEN normalized_tier = 'high' OR normalized_tier LIKE 'high %'
                  THEN 3
                ELSE 4
              END ASC,
              COALESCE(w.citation_count, 0) DESC,
              COALESCE(w.pub_year, 0) DESC,
              COALESCE(w.title, '') ASC,
              w.id ASC
            LIMIT ?
            """,
            (*subdomains, _SEED_CITATION_FLOOR, limit),
        ).fetchall()
        return tuple(
            _CorpusRow(
                work_id=str(row[0]),
                title=str(row[1] or ""),
                abstract=str(row[2] or ""),
                pub_year=int(row[3] or 0),
                evidence_tier=str(row[4] or ""),
                citation_count=int(row[5] or 0),
                subdomain_id=str(row[6] or ""),
            )
            for row in rows
        )

    @staticmethod
    def _fetch_subjects(conn: sqlite3.Connection, work_ids: Iterable[str]) -> tuple[_CorpusSubject, ...]:
        ids = tuple(dict.fromkeys(work_ids))
        if not ids:
            return ()
        placeholders = ", ".join("?" for _ in ids)
        rows = conn.execute(
            f"""
            SELECT ws.work_id, COALESCE(s.value, '')
            FROM work_subjects AS ws
            JOIN subjects AS s ON s.id = ws.subject_id
            WHERE ws.work_id IN ({placeholders})
            ORDER BY ws.work_id ASC, s.id ASC
            """,
            ids,
        ).fetchall()
        return tuple(_CorpusSubject(work_id=str(row[0]), value=str(row[1] or "")) for row in rows if row[1])

    @staticmethod
    def _fetch_identifiers(conn: sqlite3.Connection, work_ids: Iterable[str]) -> dict[str, _CorpusIdentifiers]:
        ids = tuple(dict.fromkeys(work_ids))
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        rows = conn.execute(
            f"""
            SELECT work_id, LOWER(COALESCE(scheme, '')), COALESCE(value, '')
            FROM identifiers
            WHERE work_id IN ({placeholders})
              AND LOWER(COALESCE(scheme, '')) IN ('pmid', 'doi', 'pmcid')
              AND COALESCE(value, '') <> ''
            ORDER BY work_id ASC, scheme ASC, value ASC
            """,
            ids,
        ).fetchall()

        collected: dict[str, dict[str, str]] = {}
        for work_id, scheme, value in rows:
            work_key = str(work_id)
            scheme_key = str(scheme).casefold()
            if scheme_key not in {"pmid", "doi", "pmcid"}:
                continue
            collected.setdefault(work_key, {}).setdefault(scheme_key, str(value).strip())

        return {
            work_id: _CorpusIdentifiers(
                pmid=values.get("pmid"),
                doi=values.get("doi"),
                pmcid=values.get("pmcid"),
            )
            for work_id, values in collected.items()
        }

    @staticmethod
    def _extract_seed_sources(
        rows: tuple[_CorpusRow, ...],
        identifiers_by_work_id: dict[str, _CorpusIdentifiers],
        limit: int,
    ) -> tuple[SeedSource, ...]:
        if limit <= 0:
            return ()

        candidates = [row for row in rows if _is_seed_candidate(row)]
        candidates.sort(key=_seed_sort_key)

        seeds: list[SeedSource] = []
        for row in candidates[:limit]:
            identifiers = identifiers_by_work_id.get(row.work_id, _CorpusIdentifiers())
            provenance = [
                ExpansionProvenance(
                    source="local_corpus",
                    field_path="works.id",
                    matched_value=row.work_id,
                    notes=(
                        f"subdomain_id={row.subdomain_id}; evidence_tier={row.evidence_tier}; "
                        f"citation_count={row.citation_count}; pub_year={row.pub_year}"
                    ),
                )
            ]
            for scheme, value in (
                ("pmid", identifiers.pmid),
                ("doi", identifiers.doi),
                ("pmcid", identifiers.pmcid),
            ):
                if value:
                    provenance.append(
                        ExpansionProvenance(
                            source="local_corpus",
                            field_path=f"identifiers.{scheme}",
                            matched_value=value,
                            notes=f"work_id={row.work_id}",
                        )
                    )

            seeds.append(
                SeedSource(
                    id=f"local_corpus:{row.work_id}",
                    title_hint=row.title,
                    pmid=identifiers.pmid,
                    doi=identifiers.doi,
                    pmcid=identifiers.pmcid,
                    work_id=row.work_id,
                    tier=row.evidence_tier,
                    provenance=tuple(provenance),
                )
            )

        return tuple(seeds)

    @staticmethod
    def _extract_terms(
        rows: tuple[_CorpusRow, ...],
        subjects: tuple[_CorpusSubject, ...],
        *,
        quarantine: bool,
    ) -> tuple[ExpansionTerm, ...]:
        by_work_subjects: dict[str, list[str]] = {}
        for subject in subjects:
            by_work_subjects.setdefault(subject.work_id, []).append(subject.value)

        evidence: dict[str, _TermEvidence] = {}
        for row in rows:
            field_values: tuple[tuple[str, str], ...] = (
                *(("subjects.value", value) for value in by_work_subjects.get(row.work_id, [])),
                ("works.title", row.title),
                ("works.abstract", row.abstract),
            )
            for field_path, value in field_values:
                if not value:
                    continue
                for known in _matches_known_terms(value):
                    key = known.canonical.casefold()
                    matched = _matched_text(known.pattern, value) or known.canonical
                    notes = ""
                    if quarantine:
                        notes = f"off-target subdomain {row.subdomain_id}; quarantined retrieval prior only"
                    provenance = ExpansionProvenance(
                        source="local_corpus",
                        field_path=field_path,
                        matched_value=matched,
                        notes=notes,
                    )
                    existing = evidence.get(key)
                    if existing is None:
                        evidence[key] = _TermEvidence(
                            canonical=known.canonical,
                            aliases={matched},
                            concept_type=known.concept_type,
                            confidence=known.confidence,
                            citation_count=row.citation_count,
                            title=row.title,
                            provenance=[provenance],
                        )
                        continue

                    existing.aliases.add(matched)
                    existing.confidence = max(existing.confidence, known.confidence)
                    existing.citation_count = max(existing.citation_count, row.citation_count)
                    if row.title and (not existing.title or row.title < existing.title):
                        existing.title = row.title
                    if len(existing.provenance) < _MAX_PROVENANCE_PER_TERM:
                        existing.provenance.append(provenance)

        return tuple(
            ExpansionTerm(
                canonical=item.canonical,
                aliases=tuple(sorted(item.aliases, key=str.casefold)),
                concept_type=item.concept_type,
                confidence=item.confidence,
                provenance=tuple(item.provenance),
            )
            for item in sorted(evidence.values(), key=_evidence_sort_key)
        )

    @staticmethod
    def _bound_terms(terms: tuple[ExpansionTerm, ...], limit: int) -> tuple[ExpansionTerm, ...]:
        if limit <= 0:
            return ()
        return terms[:limit]


def _case_keyword_blob(
    case: CaseSpec,
    family: ProcedureFamily | None,
    profile: ProfileName,
) -> str:
    values: list[str] = [case.raw_input, profile]
    for field_name in (
        "pathology",
        "procedure",
        "approach",
        "procedure_family",
        "broad_profile",
        "level_or_segment",
        "anatomic_location",
    ):
        value = getattr(case, field_name).value
        if value:
            values.append(value)
    if family is not None:
        values.append(getattr(family, "id", ""))
        values.append(getattr(family, "name", ""))
    return " ".join(values).casefold()


def _looks_like_thrombectomy(text: str) -> bool:
    if _THROMBECTOMY_CUE_RE.search(text):
        return True

    # Spec M1 occlusion-like cases into the stroke thrombectomy prior bucket, but
    # keep standalone M1 conservative: M1 can also denote nonvascular anatomy
    # (e.g., motor cortex).  Require occlusion-like pathology and vascular context
    # rather than allowing bare "M1" to imply thrombectomy.
    if _M1_OCCLUSION_CUE_RE.search(text):
        return True
    if not _M1_SEGMENT_CUE_RE.search(text) or _looks_like_aneurysm(text):
        return False
    return bool(_OCCLUSION_PATHOLOGY_RE.search(text) and _VASCULAR_CONTEXT_RE.search(text))


def _looks_like_aneurysm(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:aneurysm|subarachnoid|sah|coiling|clipping|aneurysm_sah)\b",
            text,
            re.I,
        )
    )


def _matches_known_terms(value: str) -> tuple[_KnownTerm, ...]:
    return tuple(known for known in _KNOWN_TERMS if known.pattern.search(value))


def _matched_text(pattern: re.Pattern[str], value: str) -> str | None:
    match = pattern.search(value)
    if match is None:
        return None
    return " ".join(match.group(0).split())


def _normalized_tier(tier: str) -> str:
    return " ".join(tier.replace("-", "_").split()).casefold()


def _seed_tier_priority(tier: str) -> int:
    normalized = _normalized_tier(tier)
    if normalized in _SEED_TIER_PRIORITIES:
        return _SEED_TIER_PRIORITIES[normalized]
    if "guideline" in normalized or "consensus" in normalized:
        return _SEED_TIER_PRIORITIES["guideline"]
    if "meta_analysis" in normalized or "meta analysis" in normalized:
        return _SEED_TIER_PRIORITIES["meta_analysis"]
    if "rct" in normalized or "randomized controlled trial" in normalized or "randomised controlled trial" in normalized:
        return _SEED_TIER_PRIORITIES["rct"]
    if normalized == "high" or normalized.startswith("high "):
        return _SEED_TIER_PRIORITIES["high"]
    return len(_SEED_TIER_PRIORITIES)


def _is_seed_candidate(row: _CorpusRow) -> bool:
    return _seed_tier_priority(row.evidence_tier) < len(_SEED_TIER_PRIORITIES) or row.citation_count >= _SEED_CITATION_FLOOR


def _seed_sort_key(row: _CorpusRow) -> tuple[int, int, int, str, str]:
    return (
        _seed_tier_priority(row.evidence_tier),
        -row.citation_count,
        -row.pub_year,
        row.title.casefold(),
        row.work_id.casefold(),
    )


def _evidence_sort_key(item: _TermEvidence) -> tuple[float, int, str, str]:
    return (-item.confidence, -item.citation_count, item.title.casefold(), item.canonical.casefold())
