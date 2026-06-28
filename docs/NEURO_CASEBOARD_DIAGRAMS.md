# neuro-caseboard — Architecture & Data-Flow Diagrams

Companion figures to `NEURO_CASEBOARD_ARCHITECTURE.md`. Reflects the `master` branch (synced to `a8b90d9`). Mermaid renders on GitHub.

### Figure 1 — System context and high-level architecture
The five product subsystems (P1–P5) and how they connect to the user surfaces and the external services (the OpenRouter and Vertex Gemini LLMs, the LanceDB index, the textbook corpus, and PubMed).

```mermaid
flowchart LR
    User[Surgeon user]

    subgraph Product[neuro caseboard product]
        P5[P5 Interfaces and Deploy]
        P2[P2 Orchestration and Models]
        P1[P1 Knowledge and Retrieval Core]
        P3[P3 Verify Grade Guards Eval]
        P4[P4 Output and Rendering]
    end

    Vertex[Vertex Gemini Build briefing]
    OpenRouter[OpenRouter glm synth]
    Lance[(LanceDB index)]
    Corpus[(Textbook corpus PDFs)]
    PubMed[PubMed E utilities]

    User -->|surfaces| P5
    P5 -->|invoke engine| P2
    P2 -->|retrieve adapter| P1
    P2 -->|calls guards| P3
    P2 -->|render model| P4
    P2 -->|literature lane| PubMed
    P1 -->|hybrid search| Lance
    Corpus -->|build index| P1
    P1 -->|Ask synthesis| OpenRouter
    P2 -->|planner author| Vertex
    P3 -->|eval and feedback| P2
    P3 -->|eval probes| P1
    P4 -->|artifacts| P5
```

### Figure 2 — End-to-end case-prep data flow
A Build or Case request from dictation through intake, explore, retrieve, enrich, audit, verify/grade, compile, and render to the final Markdown and PDF artifacts, labeling the object that passes on each hop.

```mermaid
flowchart TD
    Req[Case dictation or topic]
    Intake[intake parse_dictation]
    Manifest[explore manifest LLM or deterministic]
    Prune[P3 prune_offtarget and prefs]
    Retr[retrieve adapter neuro_core]
    Enrich[caseprep enrich_manifest]
    Audit[caseprep audit_manifest]
    Figs[collect figures]
    Verify[P3 entailment dedup grade]
    Compile[compile dossier]
    Render[P4 render_md and caseboard_pdf]
    Out[case board md and pdf]

    Req -->|free text| Intake
    Intake -->|CaseContext| Manifest
    Manifest -->|QuestionManifest| Prune
    Prune -->|filtered manifest| Enrich
    Retr -->|EvidenceRecords| Enrich
    Enrich -->|enriched manifest| Audit
    Audit -->|AuditedManifest| Figs
    Audit -->|accepted papers| Compile
    Figs -->|figure records| Compile
    Verify -->|gated citations| Compile
    Compile -->|model Dossier| Render
    Render -->|markdown and pdf| Out
```

### Figure 3 — Knowledge and retrieval pipeline (neuro_core)
The build-time corpus path (ingest → chunk → embed → index, with a parallel visual/figure lane) and the query-time path (analyze → hybrid retrieve → rerank → synthesize) over the shared LanceDB index.

```mermaid
flowchart LR
    subgraph Build[Build time]
        Corpus[(Textbook PDFs)]
        Ingest[ingest PyMuPDF]
        Chunk[chunk_pages]
        Embed[BGE embed]
        Index[(chunks table and FTS)]
        FigEmbed[BiomedCLIP embed]
        FigIndex[(figures table)]
    end

    Corpus -->|extract_pages| Ingest
    Ingest -->|page text| Chunk
    Ingest -->|figure plates| FigEmbed
    Chunk -->|word windows| Embed
    Embed -->|vectors| Index
    FigEmbed -->|image vectors| FigIndex

    subgraph Query[Query time]
        Q[Clinical question]
        Analyze[query_analyze flash lite]
        Retrieve[hybrid_search RRF]
        Rerank[cross encoder rerank]
        Figcollect[figure_retriever guards]
        Synth[synthesize]
        Out[answer citations figures]
    end

    Q -->|embed_query| Analyze
    Analyze -->|variant| Retrieve
    Index -->|hits| Retrieve
    Retrieve -->|candidates| Rerank
    Rerank -->|top hits| Synth
    FigIndex -->|figure hits| Figcollect
    Figcollect -->|figures| Synth
    LLM[OpenRouter glm synth] -->|prose| Synth
    Synth -->|QueryResult| Out
```

### Figure 4 — Verification, grading and evaluation loop
The in-engine correctness gates (entailment, answer-verify, evidence-grade, prune, dedup), the offline eval/monitor harness that scores run traces and gates merges, and the surgeon-in-the-loop feedback that distills preferences back into the pipeline.

```mermaid
flowchart TD
    subgraph Engine[Build and Ask engine]
        Compile[compile.py]
        Pipeline[pipeline.py]
        QA[qa.py]
    end

    subgraph Guards[P3 in engine guards]
        Entail[entailment should_cite]
        Verify[answer_verify]
        Grade[evidence_grade]
        Prune[guard prune_offtarget]
        Dedup[dedup sections]
    end

    Compile -->|snippet hypothesis| Entail
    Compile -->|claim signals| Grade
    Compile -->|sections| Dedup
    Pipeline -->|manifest topic| Prune
    QA -->|answer premises| Verify
    Entail -->|gated citations| Compile
    Verify -->|verification| QA

    subgraph Eval[P3 eval and monitor]
        Harness[eval harness case figure]
        Bench[evaluation run_benchmark]
        Gate[quality_gate vs BASELINE]
        Monitor[monitor detectors]
    end

    Pipeline -->|run traces| Harness
    QA -->|run traces| Harness
    Harness -->|scores| Gate
    Bench -->|manifests reports| Monitor
    Monitor -->|regressions| Gate
    Gate -.->|gates merges| Pipeline

    subgraph Loop[Surgeon in the loop]
        Feedback[feedback CaseFeedback]
        Prefs[preferences distill]
    end

    Surgeon[Surgeon marks] -->|wrong missing| Feedback
    Feedback -->|marks JSON| Prefs
    Prefs -->|preference rules| Pipeline
```

### Figure 5 — Interfaces and deployment
The four surfaces (CLI, Streamlit, FastAPI, React SPA) all forwarding to the same P2 engine, the P4 presenter they reuse, and the packaging path where Docker and serve_phone host the FastAPI process for browser and phone access.

```mermaid
flowchart LR
    Term[Terminal user]
    Browser[Browser user]
    Phone[Phone on LAN]

    subgraph Surfaces[P5 surfaces]
        CLI[caseboard CLI]
        Streamlit[Streamlit app]
        API[FastAPI server]
        Web[React Vite SPA]
    end

    Engine[P2 engine pipeline and qa]
    Render[P4 board_view and renderers]

    subgraph Infra[Packaging and deploy]
        Docker[Docker image to GHCR]
        ServePhone[serve_phone uvicorn]
        CI[GitHub Actions CI and CD]
    end

    Term -->|argv| CLI
    Browser -->|passcode| Streamlit
    Browser -->|HTTP| Web
    Phone -->|LAN HTTP| ServePhone
    Web -->|api proxy| API
    ServePhone -->|hosts| API
    CLI -->|answer_question| Engine
    API -->|build and ask| Engine
    Streamlit -->|engine calls| Engine
    Engine -->|models| Render
    Render -->|board payload| Streamlit
    API -->|JSON and SPA| Web
    CI -->|build push| Docker
    Docker -->|runs| API
```

### Figure 6 — Output and rendering (P4)
How the two P2 models reach shippable artifacts: the dual renderer stacks (Chromium HTML driven by the exec_navy theme, and the offline fpdf2 fallback with guaranteed glyphs), the figure lanes that feed them, and the Markdown / Streamlit presenters. `pipeline` picks the stack by style env plus a Chromium probe.

```mermaid
flowchart TD
    Dossier[P2 model Dossier]
    Bundle[P2 OperativeBriefingBundle]
    Dispatch[pipeline render dispatch]
    Style{style env and chromium probe}

    subgraph HTMLStack[Chromium HTML to PDF]
        Theme[exec_navy print theme]
        CasePDF[caseboard_pdf]
        BriefPDF[briefing_pdf]
        OpPDF[operative_briefing_pdf fit ladder]
    end

    subgraph Offline[fpdf2 offline fallback]
        RenderPDF[render_pdf]
        ClinPDF[render_briefing_clinical_pdf]
        Fonts[fpdf_base DejaVu and ascii_fallback]
    end

    subgraph FigLanes[figure lanes]
        Captions[captions complete and relevance]
        BriefFigs[briefing_figures select]
        Gen[figures_gen author guard render]
    end

    MD[render_md markdown]
    BoardView[board_view Streamlit payload]
    PDFout[PDF artifact]

    Dossier --> Dispatch
    Bundle --> OpPDF
    Dispatch --> Style
    Style -->|signal or print| CasePDF
    Style -->|clinical or no chromium| RenderPDF
    Theme --> CasePDF
    Theme --> BriefPDF
    Theme --> OpPDF
    Fonts --> RenderPDF
    Fonts --> ClinPDF
    CasePDF --> PDFout
    OpPDF --> PDFout
    RenderPDF --> PDFout
    Gen -->|FigureItem PNG| Dossier
    Captions --> Dossier
    BriefFigs --> Bundle
    Dossier --> MD
    Dossier --> BoardView
```
