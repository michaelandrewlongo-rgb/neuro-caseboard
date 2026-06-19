"""Curated high-yield neurointerventional topics for the corpus gap audit (BACKLOG P1 #3).

Weights are editorial (1..5): ``consequence`` = clinical harm if the corpus lacks the topic;
``frequency`` = how often it is queried. Seeded with the three gaps named in the operator brief
plus adjacent high-consequence topics; extend as coverage priorities evolve."""
from neuro_core.corpus_audit import Topic

HIGH_YIELD_TOPICS: list[Topic] = [
    Topic("intraprocedural-aneurysm-rupture-rescue",
          "Intraprocedural aneurysm rupture rescue",
          "intraprocedural aneurysm rupture management during coiling rescue", 5, 4),
    Topic("eca-dangerous-anastomoses",
          "ECA dangerous anastomoses",
          "external carotid artery dangerous anastomoses to ICA and vertebral", 5, 3),
    Topic("quantitative-procedural-outcome-rates",
          "Quantitative procedural outcome / complication / retreatment rates",
          "aneurysm coiling occlusion complication retreatment rates outcomes", 4, 5),
    Topic("thrombectomy-recanalization-rates",
          "Thrombectomy recanalization (TICI) rates",
          "mechanical thrombectomy TICI recanalization first-pass outcome rates", 4, 5),
    Topic("flow-diverter-occlusion-rates",
          "Flow diverter occlusion / complication rates",
          "flow diverter pipeline occlusion rate delayed rupture complication", 4, 4),
    Topic("contrast-induced-neurotoxicity",
          "Contrast-induced neurotoxicity / nephropathy",
          "contrast induced neurotoxicity encephalopathy nephropathy neurointervention", 3, 3),
    Topic("groin-access-complications",
          "Arterial access-site complications",
          "femoral radial access site complication pseudoaneurysm hematoma", 3, 4),
    Topic("vasospasm-endovascular-management",
          "Endovascular vasospasm management",
          "cerebral vasospasm intra-arterial verapamil angioplasty management", 4, 4),
]
