# Live Blind Image-Judge — generated schematics (2026-06-16)

Vision judge: **gemini-2.5-pro** (vertex). Figure specs authored by the active provider (vertex); rendered by the deterministic PIL renderer. Each PNG graded blindly for conceptual correctness, case-specificity (side/level/region), plausibility, labels, and schematic-clarity. Pass = overall >=8/10.

**Cost: $0 — graded on Vertex/Gemini (GCP free credit).**

| case | image | overall | concept | case-spec | plaus | labels | schem | side | lvl | $ |
|---|---|---|---|---|---|---|---|---|---|---|
| spine_acdf_c56 | case-fig-01.png | 10 | 9 | 10 | 9 | 10 | 10 | True | True | 0.0000 |
| spine_acdf_c56 | case-fig-02.png | 4 | 2 | 5 | 1 | 3 | 10 | n/a | True | 0.0000 |
| skullbase_vs_retrosigmoid | case-fig-01.png | 10 | 10 | 10 | 10 | 10 | 10 | True | True | 0.0000 |
| skullbase_vs_retrosigmoid | case-fig-02.png | 10 | 10 | 10 | 10 | 10 | 10 | True | True | 0.0000 |
| functional_awake_glioma | case-fig-01.png | 10 | 10 | 10 | 10 | 10 | 10 | True | True | 0.0000 |
| functional_awake_glioma | case-fig-02.png | 10 | 10 | 10 | 10 | 10 | 10 | True | True | 0.0000 |
| vascular_mca_clip | case-fig-01.png | 3 | 8 | 9 | 3 | 2 | 10 | True | True | 0.0000 |
| vascular_mca_clip | case-fig-02.png | ERROR | | | | | | | | judge: HTTPSConnectionPool(host='oauth2.googleapis.com', port=443): Max retries exceeded with url: /token (Caused by NameResolutionError("<urllib3.connection.HTTPSConn |
| neurooncology_convexity_meningioma | case-fig-01.png | 4 | 5 | 4 | 3 | 4 | 10 | True | True | 0.0000 |
| neurooncology_convexity_meningioma | case-fig-02.png | 9 | 9 | 10 | 10 | 5 | 10 | True | True | 0.0000 |
| pediatric_posterior_fossa_medulloblastoma | case-fig-01.png | ERROR | | | | | | | | judge: HTTPSConnectionPool(host='oauth2.googleapis.com', port=443): Max retries exceeded with url: /token (Caused by NameResolutionError("<urllib3.connection.HTTPSConn |
| pediatric_posterior_fossa_medulloblastoma | case-fig-02.png | ERROR | | | | | | | | judge: HTTPSConnectionPool(host='oauth2.googleapis.com', port=443): Max retries exceeded with url: /token (Caused by NameResolutionError("<urllib3.connection.HTTPSConn |

## Aggregate
- Figures graded: **9**
- Mean overall: **7.8/10**
- Passing (>=8/10): **6/9**
- OpenRouter spend: **$0.0000** of $3.00 cap

### spine_acdf_c56 / case-fig-01.png — overall 10/10
caption: Schematic (not a radiograph): operative corridor to C5-6.
- The label 'structure to preserve' is generic; specifying the key structures for an anterior cervical approach (e.g., carotid sheath, esophagus/trachea) would be more informative, though its absence is not a critical flaw in this abstract diagram.

### spine_acdf_c56 / case-fig-02.png — overall 4/10
caption: Schematic (not a radiograph): structures around C5-6.
- Anatomical layout is highly abstract and implausible; it does not represent the spatial relationships of structures in an anterior cervical approach.
- Labels for structures at risk are dangerously generic (e.g., 'vascular structure', 'structure at risk (medial)'). They should be specific (e.g., 'Recurrent Laryngeal Nerve', 'Carotid Sheath').
- The schematic drawing itself has no laterality; it would be identical for a left-sided approach and does not incorporate the specified 'right' side in any meaningful way.

### vascular_mca_clip / case-fig-01.png — overall 3/10
caption: Schematic (not a radiograph): Vascular configuration of a left MCA bifurcation aneurysm. The diagram shows the parent M1 segment, the aneurysm at the bifurcation, the efferent M2 trunks, and nearby perforating arteries.
- The labels for the M2 superior and inferior trunks are swapped. The vessel labeled 'M2 Inferior Trunk' is in the superior position on the diagram, and the vessel labeled 'M2 Superior Trunk' is in the inferior position. This is a critical anatomical error.
- The lenticulostriate arteries are depicted as a single point, not as small vessels arising from the M1 segment, which is anatomically inaccurate.

### neurooncology_convexity_meningioma / case-fig-01.png — overall 4/10
caption: Schematic (not a radiograph): operative corridor to right frontal convexity.
- The diagram is overly abstract and does not represent any recognizable anatomy for a frontal craniotomy.
- The title text is garbled and repetitive ('right right frontal convexity convexity...').
- The label 'structure to preserve' is too generic to be clinically useful. It should specify relevant structures like the superior sagittal sinus or motor strip.
- The schematic is a generic node-and-line graph that lacks any spatial or anatomical plausibility for the stated case.

### neurooncology_convexity_meningioma / case-fig-02.png — overall 9/10
caption: Schematic (not a radiograph): structures around right frontal convexity.
- The main title is garbled and repetitive ('right right frontal convexity convexity...').

