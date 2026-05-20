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
├── README.md
├── anatomy.md
├── approach.md
├── literature.md
├── complications.md
└── resource-links.html
```

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
