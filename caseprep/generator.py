"""Generate structured case-prep output folder."""

import webbrowser
from pathlib import Path

from .links import build_search_links
from .renderers.html import render_resource_links_html
from .schema import build_caseprep_schema, render_caseprep_files

RESOURCE_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Resource Links — {topic}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 700px; margin: 2em auto; padding: 0 1em; }}
  h1 {{ font-size: 1.4em; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ margin: 0.5em 0; }}
  a {{ color: #1a56db; }}
</style>
</head>
<body>
<h1>Resource Links — {topic}</h1>
<ul>
{link_items}
</ul>
</body>
</html>
"""


def _slugify(topic: str) -> str:
    """Turn a topic string into a filesystem-safe slug."""
    return topic.strip().lower().replace(" ", "-")


def _link_items_html(links: dict[str, str]) -> str:
    return "\n".join(
        f'  <li><a href="{url}" target="_blank" rel="noopener">{name}</a></li>'
        for name, url in links.items()
    )


def _search_links_markdown(links: dict[str, str]) -> str:
    return "\n".join(f"- [{name}]({url})" for name, url in links.items())


def generate_caseprep(
    topic: str,
    output_dir: Path,
    *,
    open_browser: bool = False,
) -> Path:
    """Create a case-prep folder and populate it with structured files.

    Returns the path to the generated resource-links.html file.
    """
    slug = _slugify(topic)
    out = Path(output_dir)
    if not out.is_absolute():
        out = Path.cwd() / out
    out.mkdir(parents=True, exist_ok=True)

    links = build_search_links(topic)

    schema = build_caseprep_schema(topic)
    rendered_files = render_caseprep_files(
        schema,
        literature_summary="## Search Links\n\n" + _search_links_markdown(links),
    )
    for filename, content in rendered_files.items():
        (out / filename).write_text(content, encoding="utf-8")

    # resource-links.html
    html_content = render_resource_links_html(topic, links)
    resource_path = out / "resource-links.html"
    resource_path.write_text(html_content, encoding="utf-8")

    if open_browser:
        webbrowser.open(str(resource_path))

    return resource_path
