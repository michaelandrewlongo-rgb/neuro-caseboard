from neuro_caseboard import briefing_synth as bs
from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.briefing_model import (
    BriefingSection, DecisionAlgorithm, TreatmentModality,
    SpineEquipment, EndovascularEquipment,
)


class FakeRec:
    def __init__(self, text, citation, book="Youmans", page=10):
        self.text = text
        self.metadata = {"citation": citation, "book": book, "page": page}


class FakeRetriever:
    """Returns 1 unique record per query so the packet has stable content."""
    def __init__(self):
        self.calls = []
    def retrieve(self, query, top_n=6):
        self.calls.append(query)
        return [FakeRec(f"passage about {query[:20]}", f"Youmans p.{len(self.calls)}",
                        page=len(self.calls))]


class FakeCase:
    pathology = "ACoA aneurysm"
    procedure = "microsurgical clipping"
    def to_topic(self):
        return "ACoA aneurysm clipping"


class FakeDossier:
    sections = []  # no literature attached in this test


def test_gather_issues_one_query_per_section_and_numbers_sources():
    r = FakeRetriever()
    packet = bs.gather_briefing_evidence(FakeCase(), FakeDossier(), r)
    # one intent query per briefing section (7) + one procedure-keyed technique probe
    assert len(r.calls) == len(bs.SECTION_KEYS) + 1
    # textbook sources are numbered T1.. in order, deduped by citation
    ids = [t["ref_id"] for t in packet.textbook]
    assert ids == [f"T{i+1}" for i in range(len(ids))]
    assert "T1" in packet.prompt_block


def test_gather_adds_procedure_keyed_technique_probe_decoupled_from_pathology():
    """The per-section queries are all `{case-topic} {suffix}`; the patient-specific pathology
    dominates hybrid retrieval and starves the pool of GENERAL procedural-technique knowledge
    (e.g. stent-coiling jailing/trans-cell). gather must ALSO issue a procedure-keyed probe —
    the planned operation + subspecialty deployment vocab, WITHOUT the pathology. (V4 SAC feedback)"""
    seen = []

    class RecRetriever:
        def retrieve(self, query, top_n=6):
            seen.append(query)
            return []

    case = CaseContext(laterality="right", pathology="dissecting aneurysm",
                       procedure="stent-assisted coil embolization")
    assert bs.subspecialty_of(case) == "endovascular"
    bs.gather_briefing_evidence(case, FakeDossier(), RecRetriever())
    probe = [q for q in seen if "jailing" in q.lower()]
    assert probe, f"no procedure-keyed technique probe issued; queries={seen}"
    assert "stent-assisted coil embolization" in probe[0]       # keyed on the procedure
    assert "dissecting aneurysm" not in probe[0]                # NOT over-constrained by pathology


def test_gather_dedups_identical_citations():
    class DupRetriever:
        def retrieve(self, query, top_n=6):
            return [FakeRec("same", "Youmans p.5", page=5)]
    packet = bs.gather_briefing_evidence(FakeCase(), FakeDossier(), DupRetriever())
    assert len(packet.textbook) == 1  # all 7 queries returned the same citation


def test_parse_prose_section_priority_and_refs():
    txt = ("[critical] Secure the aneurysm early {T1, L2}\n"
           "[high] Counsel on vasospasm risk {T3}\n"
           "[optional] Consider lumbar drain {verify}\n"
           "garbage line with no tag\n")
    sec = bs.parse_prose_section("risks", "Risks", txt)
    assert isinstance(sec, BriefingSection) and sec.key == "risks"
    assert [i.priority for i in sec.items] == ["critical", "high", "optional"]
    assert sec.items[0].source_refs == ["T1", "L2"]
    assert sec.items[2].unsupported is True  # {verify} → unsupported


def test_parse_algorithm_nodes_and_edges():
    txt = ("intro prose ignored\n"
           "---ALGORITHM---\n"
           "N1 | decision | Ruptured?\n"
           "N2 | action | Secure within 72h\n"
           "N1 -> N2 | yes\n")
    algo = bs.parse_algorithm(txt)
    assert isinstance(algo, DecisionAlgorithm)
    assert [n.id for n in algo.nodes] == ["N1", "N2"]
    assert algo.edges[0].src == "N1" and algo.edges[0].condition == "yes"


def test_parse_modalities_blocks():
    txt = ("### Microsurgical clipping\n"
           "role: durable occlusion\n"
           "advantages: durable; treats wide-neck\n"
           "limitations: invasive\n"
           "preferred: yes\n"
           "refs: T1, L2\n"
           "### Endovascular coiling\n"
           "role: less invasive\n"
           "preferred: no\n")
    mods = bs.parse_modalities(txt)
    assert [m.name for m in mods] == ["Microsurgical clipping", "Endovascular coiling"]
    assert mods[0].advantages == ["durable", "treats wide-neck"]
    assert mods[0].preferred is True and mods[1].preferred is False
    assert mods[0].source_refs == ["T1", "L2"]


def test_parse_equipment_selects_schema_by_subspecialty():
    txt = ("access_strategy: transfemoral; radial backup\n"
           "devices: flow diverter; coils\n"
           "refs: T2\n")
    eq = bs.parse_equipment(txt, "endovascular")
    assert isinstance(eq, EndovascularEquipment)
    assert eq.access_strategy == ["transfemoral", "radial backup"]
    assert eq.source_refs == ["T2"]
    # spine fields on a spine schema
    eq2 = bs.parse_equipment("cage_class_sizing: PEEK 6mm\n", "spine")
    assert isinstance(eq2, SpineEquipment) and eq2.cage_class_sizing == ["PEEK 6mm"]


from neuro_caseboard.briefing_model import OperativeBriefing, BriefingReference


class FakeSynth:
    """Returns canned guided-prose per section, keyed by a marker in the user prompt."""
    def __init__(self, fail=()):
        self.fail = set(fail)
        self.seen = []
    def generate(self, system, user, images):
        key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
        self.seen.append(key)
        if key in self.fail:
            raise RuntimeError("synth down")
        if key == "modalities":
            return "### Clipping\nrole: durable\npreferred: yes\nrefs: T1\n"
        if key == "equipment":
            return "access_strategy: transfemoral\nrefs: T1\n"
        if key == "management":
            return ("[high] Treat early {T1}\n---ALGORITHM---\nN1 | decision | Ruptured?\n"
                    "N2 | action | Secure\nN1 -> N2 | yes\n")
        return f"[critical] {key} claim {{T1}}\n[optional] minor {key} note {{L1}}\n"


def _packet():
    return bs.EvidencePacket(
        textbook=[{"ref_id": "T1", "citation": "Youmans p.1", "text": "x", "book": "Youmans", "page": 1}],
        pubmed=[{"ref_id": "L1", "title": "Study", "journal": "J", "year": 2024, "pmid": "1", "doi": "", "url": ""}],
        prompt_block="...")


def test_synthesize_all_sections_land_and_refs_resolve():
    brief, refs, failed = bs.synthesize_briefing(
        FakeCase(), FakeDossier(), _packet(), FakeSynth(), subspecialty="endovascular")
    assert isinstance(brief, OperativeBriefing) and failed == []
    keys = {s.key for s in brief.sections}
    assert {"pathology", "workup", "technique", "risks", "management"} <= keys
    assert brief.modalities and brief.modalities[0].name == "Clipping"
    assert brief.equipment is not None and brief.equipment.kind == "endovascular"
    assert brief.algorithm is not None and len(brief.algorithm.nodes) == 2
    # references resolve to the packet, namespaces distinct, support map populated
    by_id = {r.ref_id: r for r in refs}
    assert by_id["T1"].kind == "textbook" and by_id["L1"].kind == "pubmed"
    assert by_id["T1"].sections  # at least one section cites T1


def test_synthesize_failure_isolation():
    brief, refs, failed = bs.synthesize_briefing(
        FakeCase(), FakeDossier(), _packet(), FakeSynth(fail=["risks"]),
        subspecialty="cranial", sleep=lambda *a: None)
    assert failed == ["risks"]
    assert all(s.key != "risks" or not s.items for s in brief.sections)  # risks empty/absent
    assert any(s.key == "technique" for s in brief.sections)             # others still land


# ---------------------------------------------------------------------------
# Grounding/§11 regression: the model writes citations INSIDE the sentence (before the period),
# not as a line-final token. parse_prose_section must still extract them into source_refs AND
# strip them from the visible text — otherwise refs are lost (wrongly "clinician-verify") and the
# {T#} markers leak onto the briefing (a §11 violation). Surfaced live on the V4 query.
# ---------------------------------------------------------------------------

def test_parse_prose_extracts_refs_despite_trailing_punctuation():
    txt = "[critical] Stent-assisted coiling treats wide-neck aneurysms {T1, L2}.\n"
    sec = bs.parse_prose_section("technique", "Technique", txt)
    it = sec.items[0]
    assert it.source_refs == ["T1", "L2"]                 # grounding restored
    assert it.unsupported is False                        # cited → supported, not clinician-verify
    assert "{" not in it.text and "}" not in it.text      # §11: no marker leak in the prose
    assert it.text == "Stent-assisted coiling treats wide-neck aneurysms."   # period kept, tidy


def test_parse_prose_strips_inline_marker_mid_sentence():
    txt = "[high] Stenting {T7} enhances coiling of wide-neck cases.\n"
    sec = bs.parse_prose_section("technique", "Technique", txt)
    it = sec.items[0]
    assert it.source_refs == ["T7"]
    assert "{" not in it.text
    assert it.text == "Stenting enhances coiling of wide-neck cases."


def test_parse_prose_dedups_refs_and_keeps_clean_line_final_case():
    # line-final markers (the pre-existing happy path) must still work; duplicate refs collapse
    txt = "[critical] Secure the aneurysm early {T1, L2}\n[optional] minor note {verify}\n"
    sec = bs.parse_prose_section("risks", "Risks", txt)
    assert sec.items[0].source_refs == ["T1", "L2"]
    assert sec.items[0].text == "Secure the aneurysm early"
    assert sec.items[1].unsupported is True               # {verify} → no resolvable ref


def test_synthesize_retries_transient_throttle():
    """A section call that fails once then succeeds must NOT end in failed_sections — the live
    Vertex-Flash throttle drops most concurrent calls; a bounded retry recovers them."""
    class FlakySynth(FakeSynth):
        def __init__(self):
            super().__init__()
            self.attempts = {}

        def generate(self, system, user, images):
            key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
            self.attempts[key] = self.attempts.get(key, 0) + 1
            if self.attempts[key] == 1:
                raise RuntimeError("429 throttled")
            return super().generate(system, user, images)

    brief, refs, failed = bs.synthesize_briefing(
        FakeCase(), FakeDossier(), _packet(), FlakySynth(),
        subspecialty="endovascular", sleep=lambda *a: None)
    assert failed == []                                   # every transient throttle recovered


def test_parse_prose_strips_square_bracket_markers():
    # The model also emits SQUARE comma-list markers (not just curly) — must extract + strip both.
    txt = "[high] Stent placement helps wide-neck aneurysms [T7, L1].\n"
    sec = bs.parse_prose_section("technique", "Technique", txt)
    it = sec.items[0]
    assert it.source_refs == ["T7", "L1"]
    assert "[" not in it.text and "]" not in it.text
    assert it.text == "Stent placement helps wide-neck aneurysms."


def test_parse_modalities_scrubs_inline_markers():
    # {verify} / [T#] markers the model drops into modality text must not leak (§11); the real
    # refs still come from the `refs:` line.
    txt = ("### Stent-assisted coiling {verify}\nrole: reconstructive {verify}\n"
           "advantages: durable [T7, L1]; low recurrence\nrefs: T7\n")
    mods = bs.parse_modalities(txt)
    m = mods[0]
    assert "{" not in m.name and "{" not in m.role
    assert all("[" not in a and "{" not in a for a in m.advantages)
    assert m.name == "Stent-assisted coiling" and m.role == "reconstructive"
    assert m.source_refs == ["T7"]


# ---------------------------------------------------------------------------
# subspecialty_of — 3-tier fallback regression tests
# ---------------------------------------------------------------------------

def test_subspecialty_of_deterministic_spine_acdf():
    """deterministic_parse("C5-6 ACDF") → to_topic()="C5-6" (level only, "ACDF" dropped),
    so tier-1 misses; tier-3 raw-dictation scan finds "acdf" → spine."""
    from neuro_caseboard.intake import deterministic_parse
    case = deterministic_parse("C5-6 ACDF")
    assert bs.subspecialty_of(case) == "spine"


def test_subspecialty_of_llm_cranial_with_spine_comorbidity():
    """An LLM-parsed cranial case whose raw_dictation contains a spine comorbidity must NOT
    be mis-routed to spine. Tier-1 classifies 'temporal lobe resection glioma' as cranial
    (no spine signal); tier-2 finds 'temporal lobe resection' + 'glioma' → no spine signal;
    tier-3 is SKIPPED because source='llm'. Result: 'cranial'."""
    # Construct directly as the LLM parse would produce it — structured fields populated,
    # source="llm", raw_dictation contains a spine comorbidity token.
    case = CaseContext(
        procedure="temporal lobe resection",
        pathology="glioma",
        surgical_goal="gross total resection",
        location="left temporal lobe",
        raw_dictation="temporal lobe resection for epilepsy; cervical spondylosis",
        source="llm",
    )
    # Confirm the regression: the old code would scan raw_dictation and find "cervical" → "spine".
    # With the fix, tier-3 is gated on source != "llm", so the cranial case stays cranial.
    assert bs.subspecialty_of(case) == "cranial"


def test_subspecialty_of_endovascular():
    """An endovascular/vascular case routes to 'endovascular'."""
    from neuro_caseboard.intake import deterministic_parse
    case = deterministic_parse("basilar tip aneurysm coiling")
    assert bs.subspecialty_of(case) == "endovascular"


# ---------------------------------------------------------------------------
# Regression tests for Fixes 1–3 (messy/realistic model output)
# ---------------------------------------------------------------------------

def test_equipment_prompt_contains_field_names():
    """build_section_prompt for the equipment section must inject the schema's snake_case field
    names so the model emits exactly those keys. Pre-fix: the prompt never lists them → any
    natural-language reply (e.g. "Positioning & monitoring:") parses to an all-empty plan."""
    from neuro_caseboard.briefing_synth import build_section_prompt, _EQUIP_CLASS
    packet = _packet()
    _, user_prompt = build_section_prompt("equipment", packet, FakeCase(), "cranial")
    cls = _EQUIP_CLASS["cranial"]
    expected_fields = [n for n in cls.model_fields if n not in ("kind", "source_refs")]
    for fname in expected_fields:
        assert fname in user_prompt, (
            f"equipment prompt is missing snake_case field name '{fname}'; "
            f"the model will use natural-language keys that parse_equipment won't match")


def test_synthesize_dangling_ref_pruned_and_unsupported():
    """A prose item citing only T9 (not in the 1-source packet) must have source_refs cleared
    and unsupported flipped to True after synthesize_briefing. Pre-fix: T9 survives in
    source_refs and unsupported stays False, violating the grounding invariant."""

    class DanglingFakeSynth:
        def generate(self, system, user, images):
            key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
            if key == "pathology":
                return "[critical] some out-of-packet finding {T9}\n"
            if key == "modalities":
                return "### Clipping\nrole: durable\npreferred: yes\nrefs: T1\n"
            if key == "equipment":
                return "access_strategy: transfemoral\nrefs: T1\n"
            if key == "management":
                return ("[high] Treat early {T1}\n---ALGORITHM---\n"
                        "N1 | decision | Ruptured?\nN2 | action | Secure\nN1 -> N2 | yes\n")
            return f"[critical] {key} claim {{T1}}\n"

    brief, refs, _ = bs.synthesize_briefing(
        FakeCase(), FakeDossier(), _packet(), DanglingFakeSynth(), subspecialty="endovascular")

    pathology_sec = next(s for s in brief.sections if s.key == "pathology")
    critical_item = pathology_sec.items[0]

    # Dangling T9 must be pruned from source_refs
    assert "T9" not in critical_item.source_refs, (
        "T9 was not pruned even though it has no entry in the packet")
    # item had refs but all dangling → unsupported must be flipped True
    assert critical_item.unsupported is True, (
        "item cited T9 (all dangling) but unsupported was not set True")
    # no BriefingReference with ref_id T9 must exist
    ref_ids = {r.ref_id for r in refs}
    assert "T9" not in ref_ids, "T9 appeared in assembled references despite not being in packet"


def test_parse_algorithm_node_with_arrow_in_label_is_not_dropped():
    """A node line whose label contains '->' must be parsed as a node, not dropped as an edge.
    Pre-fix: the '->' check runs before the '| >= 2' check → the line is misrouted to the edge
    branch, the node is silently dropped, and the algorithm graph is incomplete."""
    txt = ("intro prose ignored\n"
           "---ALGORITHM---\n"
           "N1 | decision | Guide in vessel?\n"
           "N2 | action | advance wire -> ICA\n"
           "N1 -> N2 | yes\n")
    algo = bs.parse_algorithm(txt)
    assert algo is not None
    node_ids = [n.id for n in algo.nodes]
    assert "N2" in node_ids, (
        f"N2 node was dropped (got {node_ids}); "
        "a label containing '->' must not be misrouted to the edge branch")
    n2 = next(n for n in algo.nodes if n.id == "N2")
    assert "advance wire -> ICA" == n2.label
