# Live Blind Image-Judge — generated schematics (2026-06-16)

Vision judge: **gemini-2.5-pro** (vertex). Figure specs authored by the active provider (vertex); rendered by the deterministic PIL renderer. Each PNG graded blindly for conceptual correctness, case-specificity (side/level/region), plausibility, labels, and schematic-clarity. Pass = overall >=8/10.

**Cost: $0 — graded on Vertex/Gemini (GCP free credit).**

| case | image | overall | concept | case-spec | plaus | labels | schem | side | lvl | $ |
|---|---|---|---|---|---|---|---|---|---|---|
| spine_acdf_c56 | case-fig-01.png | 10 | 10 | 10 | 9 | 10 | 10 | True | True | 0.0000 |
| spine_acdf_c56 | case-fig-02.png | 1 | 4 | 5 | 1 | 1 | 10 | n/a | False | 0.0000 |
| skullbase_vs_retrosigmoid | case-fig-01.png | 9 | 8 | 10 | 6 | 9 | 10 | True | True | 0.0000 |
| skullbase_vs_retrosigmoid | case-fig-02.png | 3 | 2 | 3 | 2 | 4 | 10 | True | True | 0.0000 |
| functional_awake_glioma | case-fig-01.png | 10 | 10 | 10 | 9 | 10 | 10 | True | True | 0.0000 |
| functional_awake_glioma | case-fig-02.png | 10 | 10 | 10 | 10 | 10 | 10 | True | True | 0.0000 |
| vascular_mca_clip | case-fig-01.png | 10 | 10 | 10 | 10 | 10 | 10 | True | True | 0.0000 |
| vascular_mca_clip | case-fig-02.png | 10 | 10 | 10 | 10 | 10 | 10 | True | True | 0.0000 |
| neurooncology_convexity_meningioma | case-fig-01.png | 10 | 10 | 10 | 10 | 9 | 10 | True | True | 0.0000 |
| neurooncology_convexity_meningioma | case-fig-02.png | 10 | 10 | 10 | 10 | 10 | 10 | True | True | 0.0000 |
| pediatric_posterior_fossa_medulloblastoma | case-fig-01.png | 10 | 10 | 10 | 10 | 10 | 10 | n/a | True | 0.0000 |
| pediatric_posterior_fossa_medulloblastoma | case-fig-02.png | 1 | 2 | 10 | 0 | 10 | 10 | True | True | 0.0000 |

## Aggregate
- Figures graded: **12**
- Mean overall: **7.8/10**
- Passing (>=8/10): **9/12**
- OpenRouter spend: **$0.0000** of $3.00 cap

### spine_acdf_c56 / case-fig-01.png — overall 10/10
caption: Schematic (not a radiograph): Illustrates the right-sided anterior surgical corridor to the C5-6 disc space, between the medially retracted visceral column and the laterally retracted carotid sheath.
- The circular layout is a highly abstract representation of an axial cross-section; while the relative positions of anatomical structures are correct, the format may not be immediately intuitive to all viewers.

### spine_acdf_c56 / case-fig-02.png — overall 1/10
caption: Schematic (not a radiograph): Depicts the surgical goal at C5-6, showing removal of the compressive disc and osteophytes, followed by placement of an interbody graft and anterior plate for fusion.
- The labels for the C5 and C6 vertebral bodies are swapped. In the cervical spine, C5 is superior to C6. The diagram incorrectly places C6 superior to C5.
- The diagram is extremely abstract and does not clearly depict the anatomical relationships or the surgical procedure. The pathology and surgical hardware are represented as a disconnected key/legend rather than being integrated into the anatomical drawing.
- The vertebral bodies are depicted as simple empty boxes, failing to convey any meaningful anatomical information.

### skullbase_vs_retrosigmoid / case-fig-01.png — overall 9/10
caption: Schematic (not a radiograph): operative corridor to cerebellopontine angle.
- The schematic is extremely abstract, representing anatomy as a network diagram rather than a spatial map. This reduces its anatomical plausibility.
- The label 'structure to preserve' is generic. Specifying the facial nerve (CN VII) would be more informative for a vestibular schwannoma case.

### skullbase_vs_retrosigmoid / case-fig-02.png — overall 3/10
caption: Schematic (not a radiograph): structures around cerebellopontine angle.
- The schematic is overly abstract and simplified to the point of being uninformative for a surgical procedure.
- The actual pathology, the vestibular schwannoma, is not depicted. The central node is labeled 'cerebellopontine angle', which is a space, not a structure or pathology.
- Labels are too generic. 'Structure at risk (medial)', 'structure at risk (lateral)', and 'vascular structure' fail to identify the critical anatomy for this case, such as the facial nerve (CN VII), vestibulocochlear nerve (CN VIII), brainstem, or specific vessels like AICA.
- The spatial layout is arbitrary and does not represent the actual anatomical relationships within the cerebellopontine angle.
- The diagram provides no more information than the text of the case description itself.

### neurooncology_convexity_meningioma / case-fig-01.png — overall 10/10
caption: Schematic (not a radiograph): Trajectory for a right frontal craniotomy, showing the layered approach from scalp to the convexity meningioma, with respect to the underlying brain and medial superior sagittal sinus.
- The main title is truncated ('...Conv...').
- The footer caption is truncated ('...to the c...').
- The label 'Scalp and Galea' is partially obscured or truncated, appearing as 'Sco and Galea' in the OCR.

### pediatric_posterior_fossa_medulloblastoma / case-fig-02.png — overall 1/10
caption: Schematic (not a radiograph): An anatomic map of the fourth ventricle, illustrating the position of the medulloblastoma relative to the floor, roof, and surrounding critical neural and vascular structures.
- The spatial relationships between anatomical structures are completely implausible and misleading.
- The diagram depicts a superior-to-inferior linear relationship between 'Brainstem Nuclei', 'Floor of Fourth Ventricle', and 'Medulloblastoma', which is anatomically incorrect. The nuclei are within the floor, and the tumor is posterior to the floor.
- The 'Roof of Fourth Ventricle' is incorrectly placed inferior to both the tumor and the 'Foramen of Magendie'. Medulloblastomas typically arise from the roof, which is superior/posterior to the foramen.
- The diagram is so abstract and anatomically incorrect that it fails to provide any useful conceptual map for the surgeon and could cause confusion.

