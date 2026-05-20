"""CLI entry point for caseprep."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .generator import generate_caseprep, _slugify
from .pdfs import format_pdf_results, search_local_pdfs


def _cmd_generate(args: argparse.Namespace) -> int:
    """Generate a case prep folder (original CLI behaviour)."""
    output_dir = Path(args.output or (_slugify(args.topic) + "-caseprep"))

    resource_path = generate_caseprep(
        args.topic,
        output_dir,
        open_browser=args.open,
    )

    print(f"Case prep generated → {output_dir.resolve()}")
    print(f"Resource links → {resource_path}")

    if args.local_pdfs:
        print(f"\nSearching local PDFs in {args.local_pdfs} …")
        results = search_local_pdfs(args.topic, args.local_pdfs)
        print(format_pdf_results(results))

    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    """Launch the CasePrep web dashboard."""
    import uvicorn
    from .web import app

    host = args.host
    port = args.port
    url = f"http://{host}:{port}"
    print(f"  CasePrep dashboard → {url}")
    print(f"  API docs           → {url}/docs")
    print(f"  Press Ctrl+C to stop\n")

    if args.open:
        import webbrowser
        webbrowser.open(url)

    uvicorn.run(app, host=host, port=port, log_level=args.log_level)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run caseprep.  Returns exit code."""
    parser = argparse.ArgumentParser(
        prog="caseprep",
        description="Generate structured neurosurgical case prep materials.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"caseprep {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── generate (default) ──────────────────────────────────────────────
    gen = subparsers.add_parser(
        "generate",
        help="Generate a case prep folder (default command)",
    )
    gen.add_argument(
        "topic",
        help="Case or topic string (e.g. 'vestibular schwannoma')",
    )
    gen.add_argument(
        "-o", "--output",
        type=Path,
        help="Output directory (default: {slug}-caseprep/)",
    )
    gen.add_argument(
        "--open",
        action="store_true",
        help="Open resource-links.html in the default browser after generation.",
    )
    gen.add_argument(
        "--local-pdfs",
        type=Path,
        metavar="DIR",
        help="Directory of PDFs to search for topic matches.",
    )

    # ── serve ───────────────────────────────────────────────────────────
    srv = subparsers.add_parser(
        "serve",
        help="Launch the CasePrep web dashboard",
    )
    srv.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    srv.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port (default: 8000)",
    )
    srv.add_argument(
        "--open",
        action="store_true",
        help="Open the dashboard in the default browser on startup.",
    )
    srv.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Uvicorn log level (default: info)",
    )

    # Backwards compatibility: bare `caseprep <topic>` → `caseprep generate <topic>`
    # If argv is provided and the first arg isn't a known subcommand, inject 'generate'
    _subcommands = {"generate", "serve"}
    if argv and argv[0] not in _subcommands and not argv[0].startswith("-"):
        argv = ["generate"] + list(argv)

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "serve":
        return _cmd_serve(args)
    else:
        return _cmd_generate(args)


if __name__ == "__main__":
    sys.exit(main())
