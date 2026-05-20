# caseprep

Generate structured neurosurgical case prep materials from a topic string.

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```bash
caseprep "vestibular schwannoma"
caseprep "acoustic neuroma" --open
caseprep "pituitary adenoma" -o ~/cases/pa --local-pdfs ~/papers/
```

## Output

```
vestibular-schwannoma-caseprep/
├── caseprep.yaml
├── provenance.json
├── README.md
├── 01-case-summary.md
├── 02-imaging-review.md
├── 03-anatomy-at-risk.md
├── 04-operative-plan.md
├── 05-risk-and-rescue.md
├── 06-postop-plan.md
├── 07-evidence.md
├── 08-checklists.md
├── 09-open-questions.md
├── anatomy.md          # compatibility alias for 03-anatomy-at-risk.md
├── approach.md         # compatibility alias for 04-operative-plan.md
├── literature.md       # compatibility alias for 07-evidence.md
├── complications.md    # compatibility alias for 05-risk-and-rescue.md
└── resource-links.html
```

The canonical source of truth is `caseprep.yaml`. Markdown files are rendered
from that schema for quick review. `provenance.json` records whether content is
generated, inferred, cited, user-entered, or verified. Generated clinical
content should be treated as draft material until reviewed by a clinician.

## MCP Tools

```
search_pubmed       — PubMed search with clinical filters, optional abstracts
build_caseplan      — 4-axis search → filled templates + PMC full text
generate_caseprep   — blank (fill-in-the-blanks) template scaffold
get_fulltext        — 3-tier: PMC → structured → plain abstract for a PMID
search_local_pdfs   — PyMuPDF search of local PDF files
search_radiology    — Open-i (NIH) radiology images: MRI, CT, X-ray, ultrasound
```

## Run tests

```bash
pytest -v
```
