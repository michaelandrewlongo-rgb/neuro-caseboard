# ACDF C5-6 Iteration 001 Defect List

Case: `C5-6 anterior cervical discectomy and fusion for right C6 radiculopathy from foraminal disc osteophyte complex`

Output: `/tmp/caseprep-live-acdf-c5-6-v1`

Status: **FAIL**

- Deterministic eval: **FAIL**, 40/100
- Blind clinical review: **FAIL**, 10/100
- Pass threshold: 75/100

## Summary

Cold ACDF validation shows the procedure-first architecture does **not** yet generalize from right M1 thrombectomy to ACDF. The parser correctly detects the procedure, level, side, pathology, family, and spine profile, but the generated dossier is essentially a visible skeleton: many `needs input` placeholders, weak evidence retrieval, no usable ACDF operative workflow, and no anterior-cervical rescue algorithms.

## P0 defects — block pass / clinically unsafe or misleading

### P0-1: Output claims no missing critical facts despite major missing clinical facts

Evidence:
- Build output says `missing critical facts: none`.
- Reviewer identified absent baseline neuro exam, imaging details, prior treatment, anticoagulation, graft/implant plan, approach side, airway risk, prior neck surgery, and vocal cord function when relevant.

Risk:
- Misleads user into thinking the ACDF plan is complete.

Acceptance criteria:
- ACDF builds must expose missing patient-/case-specific facts when they are absent.
- `missing critical facts: none` should only appear when required ACDF facts are actually known or explicitly not required.

### P0-2: Output labels itself not degraded despite blank or placeholder clinical sections

Evidence:
- `degraded: False` and `degradation status: not degraded`.
- Review says the dossier is essentially an empty template with many `needs input` placeholders.

Risk:
- A clinically unusable artifact is presented as a normal dossier.

Acceptance criteria:
- If core technique/anatomy/risk sections remain blank or placeholder-heavy, quality status must be degraded/insufficient.
- Deterministic eval should fail when not-degraded output has major blank ACDF sections.

### P0-3: ACDF-specific anatomy and rescue priorities are absent

Evidence:
- Anatomy score 0/20.
- Complications/rescue score 1/15.
- Missing airway hematoma rescue, RLN palsy, dysphagia/esophageal injury, vertebral artery injury, CSF leak, wrong-level surgery, hardware/graft malposition, neurologic worsening, infection, and pseudarthrosis.

Risk:
- Fails to prepare resident/fellow for the most important anterior cervical hazards.

Acceptance criteria:
- ACDF dossier must include anterior cervical anatomy at risk and operational rescue algorithms before it can pass.

## P1 defects — major quality failures

### P1-1: No stepwise C5-6 ACDF operative workflow

Missing:
- setup and positioning
- approach side considerations
- incision and platysma opening
- avascular Smith-Robinson plane
- level localization
- longus coli elevation and retractor placement
- Caspar pins/distraction
- discectomy/decompression sequence
- posterior osteophyte/PLL handling
- foraminal/uncinate decompression
- graft/cage/plate placement
- final fluoroscopy
- hemostasis, drain/closure

Acceptance criteria:
- `04-operative-plan.md` and `00-morning-of-case.md` should contain a concise but actionable ACDF sequence.

### P1-2: Parsed facts are not translated into surgical objectives

Evidence:
- Case-specificity score 2/10.
- Reviewer: output does not translate right C6 radiculopathy from C5-6 foraminal disc osteophyte into the objective of right C5-6 foraminal/uncinate decompression of the exiting C6 root.

Acceptance criteria:
- Morning page and operative plan should state the target pathology, target nerve root, side, level, and decompression objective.

### P1-3: Imaging review is generic/empty

Missing:
- MRI/CT/X-ray review for right C5-6 foraminal stenosis/disc-osteophyte
- central canal stenosis/myelomalacia
- kyphosis/lordosis
- instability
- OPLL/calcified osteophyte burden
- adjacent segment disease
- approach-side anatomy and prior surgery considerations

Acceptance criteria:
- `02-imaging-review.md` must provide an ACDF-specific imaging checklist.

### P1-4: Evidence retrieval is weak and partly broken

Evidence:
- Build warning: `Corpus: Invalid FTS query: no such column: 6`.
- Only one PubMed source retrieved.
- Reviewer judged it poorly matched: ACDR vs minimally invasive posterior cervical foraminotomy, not ACDF technique or ACDF-specific outcomes.

Acceptance criteria:
- Escape/quote spinal-level tokens such as `C5-6` for corpus FTS.
- Retrieve ACDF-relevant evidence for cervical radiculopathy, foraminal stenosis/disc-osteophyte, PCF vs ACDF, CDA vs ACDF, ACDF complications, dysphagia/RLN palsy, pseudarthrosis, and adjacent segment disease.

### P1-5: Alternatives and decision boundaries are not meaningful

Missing:
- ACDF vs posterior cervical foraminotomy
- ACDF vs cervical disc arthroplasty
- continued nonoperative care
- decision modifiers: instability, kyphosis, central stenosis/myelopathy, severe axial neck pain, calcified osteophyte/OPLL, bilateral symptoms, prior anterior surgery, dysphagia/vocal cord history

Acceptance criteria:
- Alternatives section must explain when ACDF is favored or not favored for unilateral C6 radiculopathy from foraminal disc-osteophyte.

## P2 defects — cleanup / polish

- Remove generic cranial-neurosurgery rescue language such as `declining mental status → CT head` when not relevant to ACDF.
- Remove irrelevant postop/open-question items such as antiepileptic management for routine ACDF.
- Avoid duplicate old-style files (`anatomy.md`, `approach.md`, `complications.md`, `literature.md`); the primary numbered dossier is the source of truth.

## Recommended next narrow implementation slice

**Build an ACDF procedure-specific dossier content path before broader generalization.**

Highest expected score delta:
1. Add ACDF-specific defaults/templates for morning page, imaging checklist, anatomy at risk, operative workflow, risk/rescue, postop plan, alternatives, and open questions.
2. Fix spinal-level FTS escaping/quoting for `C5-6` so corpus retrieval does not throw `no such column: 6`.
3. Add deterministic tests requiring core ACDF concepts from the canonical rubric: anterior cervical exposure, localization, recurrent laryngeal nerve, esophagus, vertebral artery, dysphagia, foraminal/uncinate decompression, graft/cage/plate.
4. Rebuild the same case and run a fresh blind review.

## Suggested acceptance gate for iteration 002

- Deterministic eval passes or improves from 40 to at least 80 with no P0 deterministic failures.
- Blind review improves by at least +40 points from 10/100, ideally crossing 50 before citation/evidence hardening.
- No `missing critical facts: none` when ACDF-specific required facts are unknown.
- No generic cranial/open-neurosurgery rescue language in ACDF primary files.
