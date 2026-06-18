# Query enrichment with NSGY_DB as a local neurosurgery prior

CasePrep uses NSGY_DB as a transparent retrieval prior, not a black-box answer generator.

## Allowed

- Add synonyms, related terms, subdomain hints, outcome terms, anatomy-at-risk terms, query templates, seed identifiers, and warnings.
- Preserve provenance for every expansion.
- Use local corpus metadata to improve PubMed/PMC retrieval.

## Not allowed

- Silently overwrite parser-derived case facts.
- Infer laterality, pathology, approach, or operative target from the most common literature cluster.
- Generate final clinical claims from local corpus priors without `EvidenceRecord` provenance.
- Build graph/embedding infrastructure before deterministic SQL-backed prior is validated.

## Laterality rule

Laterality is a case fact for operative reasoning and rendering. It is usually excluded from broad PubMed/PMC literature search strings unless the search purpose explicitly requires laterality. Laterality-sensitive retrieval examples include dominant-hemisphere/awake mapping literature, AVM eloquence or mapping queries, and spine approach-side questions such as LLIF. The decision is recorded per query in `case_fact_policy`; routine broad-query stripping should not create noisy user-facing warnings.

## PubMed query rule

PubMed queries must be rendered from structured query specs. Use MeSH terms where appropriate, `[tiab]` field tags for free-text terms and acronyms, explicit publication-date filters for current-evidence axes, and `omitted_terms` metadata when bounded alias lists are truncated.

## Seed-source rule

Landmark seed PMIDs/DOIs come first from curated CasePrep evidence packs, not from NSGY_DB. Corpus-derived identifiers may supplement and add provenance, but must not replace curated seeds. Duplicate seed sources are merged by PMID, DOI, PMCID, or work_id while preserving provenance.

## Corpus boundary

CasePrep consumes local corpus exports/adapters; it is not the corpus curation pipeline. Metadata repairs, MeSH normalization, coverage updates, and schema evolution belong upstream. The adapter should validate schema/version and degrade with warnings when the corpus is unavailable or inconsistent.
