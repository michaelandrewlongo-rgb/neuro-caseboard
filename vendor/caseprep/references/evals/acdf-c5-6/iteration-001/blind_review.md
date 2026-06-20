# Independent Spine Neurosurgery CasePrep Review

**Folder reviewed:** `/tmp/caseprep-live-acdf-c5-6-v1`
**Case input:** “C5-6 anterior cervical discectomy and fusion for right C6 radiculopathy from foraminal disc osteophyte complex”

## 1. Overall Score

**Overall: 10/100 — FAIL**

Pass threshold: 75/100.

This dossier is essentially an empty template with many `needs input` placeholders. It correctly parses the intended procedure, level, laterality, and pathology, but it does not provide usable clinical preparation for a resident/fellow before a C5-6 ACDF.

## 2. Category Scores

- **Technique / operative workflow: 1/25**
  - Identifies ACDF as the procedure but provides no real operative workflow.
  - Missing positioning, incision/exposure, level localization, disc-space confirmation, decompression sequence, uncinate/foraminal decompression, PLL handling, endplate preparation, graft/cage selection, plating, fluoroscopy, closure, drain considerations.

- **Anatomy / dangerous structures: 0/20**
  - Anatomy section is entirely `needs input`.
  - No discussion of carotid sheath, esophagus/trachea, recurrent laryngeal nerve, superior/inferior thyroid vessels, longus coli, sympathetic chain, vertebral artery, C6 nerve root, uncinate process, epidural venous plexus, dura, or level-specific landmarks.

- **Complications / rescue plans: 1/15**
  - Contains only generic neurosurgical rescue lines such as “new focal deficit” and “declining mental status.”
  - Missing ACDF-specific complications and rescue: postoperative neck hematoma/airway compromise, dysphagia, esophageal injury, RLN palsy, vertebral artery injury, CSF leak, wrong level, graft/plate malposition, C6 palsy/persistent radiculopathy, spinal cord injury, infection, pseudarthrosis.

- **Alternatives / decision boundaries: 1/10**
  - Alternatives are not meaningfully addressed.
  - Evidence mentions ACDR and posterior cervical foraminotomy, but there is no decision framework for ACDF vs posterior foraminotomy vs arthroplasty vs continued nonoperative care.

- **Evidence quality and relevance: 1/10**
  - Only one PubMed source is included.
  - The cited paper compares ACDR and minimally invasive posterior cervical foraminotomy, not ACDF technique or ACDF-specific outcomes.
  - No case-specific synthesis, no complication rates, no guideline-level evidence, and a visible retrieval warning: “Invalid FTS query: no such column: 6.”

- **Case-specificity: 2/10**
  - It correctly extracts C5-6, right-sided symptoms, and C6 radiculopathy from foraminal disc osteophyte complex.
  - However, essentially all useful patient-, imaging-, and operative-specific details are blank.
  - It does not translate “right C6 radiculopathy from C5-6 foraminal disc osteophyte complex” into the key surgical objective: right C5-6 foraminal/uncinate decompression of the exiting C6 root.

- **Readability / usability: 2/5**
  - File organization is clear and the placeholders are visible.
  - However, as a night-before/morning-of case prep document, it is not clinically usable because nearly every substantive section is empty.

- **Provenance / citation support: 2/5**
  - Provenance exists and one PMID is listed.
  - But the citation is poorly matched to the case and does not support ACDF workflow, anatomy, or rescue planning.
  - The markdown evidence section lacks meaningful citation-backed synthesis.

**Arithmetic check:** 1 + 0 + 1 + 1 + 1 + 2 + 2 + 2 = **10/100**

## 3. Top 5 Clinically Important Missing or Weak Items

1. **No ACDF operative workflow**
   - Needs a stepwise C5-6 ACDF plan: setup, right/left-sided approach preference, transverse incision, platysma, avascular plane, level confirmation, longus coli elevation, retractor placement, Caspar pins/distraction, discectomy, posterior osteophyte removal, foraminal decompression, graft/cage/plate, final fluoroscopy, hemostasis, drain/closure.

2. **No ACDF-specific anatomy at risk**
   - Should explicitly cover trachea/esophagus, carotid sheath, RLN, superior/inferior thyroid vessels, sympathetic chain, longus coli, vertebral artery lateral to uncinate, dura, spinal cord, C6 root, uncinate joints, and anatomic variant concerns.

3. **No imaging review guidance**
   - Should prompt review of MRI/CT/x-rays for C5-6 level, right foraminal stenosis/disc-osteophyte location, central canal stenosis/myelomalacia, kyphosis/lordosis, instability, OPLL, vertebral artery anatomy if relevant, osteophyte/calcification burden, and adjacent segment disease.

4. **No ACDF-specific complication and rescue plan**
   - Missing the most important rescue scenario: postoperative expanding neck hematoma with airway compromise requiring immediate bedside wound opening if necessary, anesthesia/ENT involvement, and OR return.
   - Also missing RLN palsy, dysphagia/esophageal injury, vertebral artery injury, CSF leak, wrong-level surgery, neurologic worsening, graft/plate malposition.

5. **No decision boundaries or alternatives**
   - For unilateral C6 radiculopathy from foraminal disc-osteophyte complex, should discuss when ACDF is favored versus posterior cervical foraminotomy, cervical disc arthroplasty, continued conservative therapy, or need for posterior/combined approach.
   - Should include boundaries such as instability, kyphosis, severe axial neck pain, central stenosis/myelopathy, calcified osteophyte/OPLL, bilateral symptoms, prior anterior surgery, swallowing/vocal cord history.

## 4. Unsafe, Misleading, Fabricated, or Overly Generic Content

- **Unsafe/misleading:** `Missing critical facts: none identified`
  - This is not acceptable. Many critical facts are missing: baseline neurologic exam, imaging details, prior treatment, anticoagulation, graft/implant plan, approach side, airway risk, prior neck surgery, vocal cord function if relevant.

- **Misleading confidence/degradation status**
  - The dossier says “degradation status: not degraded,” despite the output being almost entirely empty placeholders and a failed evidence query.

- **Overly generic rescue triggers**
  - “Declining mental status → CT head” is not a useful primary ACDF rescue pathway.
  - For ACDF, airway compromise, dysphagia, neck swelling, stridor, expanding hematoma, and neurologic deterioration should be prioritized.

- **Irrelevant generic open questions**
  - “Antiepileptic” appears in postop questions, which is not relevant to routine ACDF.

- **Evidence relevance is weak**
  - The single cited article is about ACDR vs minimally invasive posterior cervical foraminotomy and is not a strong support source for the planned ACDF.
  - The evidence section also states that evidence has not been synthesized.

## 5. Would This Help a Resident/Fellow Prepare?

**No, not meaningfully.**

It might remind a trainee that they need to review imaging, equipment, risks, and open questions, but it does not teach or guide the actual case. A resident/fellow using this the night before would still need to build the entire clinical prep independently.

At best, it is a skeleton checklist. It is not a case-prep dossier.

## 6. Recommended Engineering / Product Fixes

1. **Add a procedure-specific ACDF content template**
   - Populate standard C5-6 ACDF anatomy, workflow, imaging checklist, equipment, complications, postop plan, and rescue algorithms even when patient-specific data are limited.

2. **Fix search/query handling for spinal levels**
   - The evidence warning suggests `C5-6` was parsed into an invalid FTS query. Escape hyphens and level notation properly.

3. **Implement completeness gating**
   - If core clinical sections are blank, the output should be marked “insufficient / degraded,” not “not degraded.”
   - Do not state “missing critical facts: none” when required fields remain empty.

4. **Make evidence retrieval case-relevant**
   - Retrieve sources on ACDF for cervical radiculopathy, foraminal stenosis/disc-osteophyte complexes, posterior cervical foraminotomy vs ACDF, cervical disc arthroplasty vs ACDF, ACDF complications, dysphagia/RLN palsy, pseudarthrosis, and adjacent segment disease.
   - Include guideline/systematic review sources where available.

5. **Generate ACDF-specific rescue plans**
   - Mandatory rescue content should include:
     - Postop neck hematoma/airway compromise.
     - Intraoperative vertebral artery injury.
     - Esophageal injury.
     - CSF leak/dural tear.
     - New neurologic deficit.
     - Wrong-level prevention and correction.
     - Hardware/graft malposition.

6. **Use the parsed case facts clinically**
   - Convert “right C6 radiculopathy at C5-6 from foraminal disc osteophyte complex” into concrete objectives:
     - Confirm right C5-6 foraminal compression.
     - Decompress exiting right C6 root.
     - Address uncovertebral osteophyte/foraminal stenosis.
     - Confirm adequate foraminal decompression before graft placement.

7. **Improve morning-of-case page**
   - Should be a true one-page actionable summary: indication, imaging must-confirm items, approach side, equipment, key risks, stepwise plan, stop points, postop orders.

8. **Remove irrelevant generic neurosurgery content**
   - Avoid cranial/general neurosurgery rescue pathways unless relevant.
   - Replace with anterior cervical spine-specific content.

## Work Performed By Reviewer

- Reviewed the generated markdown dossier in `/tmp/caseprep-live-acdf-c5-6-v1`.
- Read the clinically relevant files, including README, morning-of-case, case summary, imaging, anatomy, operative plan, risk/rescue, postop plan, evidence, checklists, open questions, anatomy/approach/complications/literature duplicates, provenance, and caseprep YAML.
- Graded the artifact using the requested 100-point rubric.

## Files Created or Modified By Reviewer

- None. This was a read-only clinical quality review.
