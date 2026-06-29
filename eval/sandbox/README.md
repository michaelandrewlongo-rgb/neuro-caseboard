# Guidelines sandbox

Source the cheap stack, then pick an arm via INDEX_DIR:

    set -a; . ~/.config/neuro-caseboard/sandbox.env; set +a
    export INDEX_DIR=/home/michael/neuro-textbook-rag/index           # baseline arm (18)
    export INDEX_DIR=/home/michael/neuro-textbook-rag/index-sandbox   # treatment arm (60)

Both arms use the same model stack (deepseek-v4-flash + vertex gemini-2.5-flash);
the only variable is the corpus. See docs/superpowers/specs/2026-06-29-guidelines-testing-sandbox-design.md.
