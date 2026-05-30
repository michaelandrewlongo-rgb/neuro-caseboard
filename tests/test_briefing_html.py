from __future__ import annotations
import base64, json, re
from caseprep.image_bank.figure_store import FigureRecord
from caseprep.renderers.briefing_html import render_briefing_html

def _store(tmp_img):
    return [FigureRecord("image_bank","1",["aspects"],"ASPECTS template",str(tmp_img),None,
                         {"pmcid":"PMC1","pmid":"9"},[1.0,0.0]),
            FigureRecord("textbook","2",["collaterals"],"Collateral grading","",b"\x89PNG\r\n\x1a\n",
                         {"heading_path":"Stroke>Fig1"},[0.0,1.0])]

def test_marked_term_becomes_figref_with_embedded_figure(tmp_path):
    img=tmp_path/"a.jpg"; img.write_bytes(b"JPEGBYTES")
    md="## Imaging\n\nASPECTS guides EVT.\n"
    html=render_briefing_html(md,_store(img),embed_fn=lambda t:[[1.0,0.0]],floor=0.2)
    assert 'class="figref"' in html and 'data-fig="image_bank:1"' in html
    assert "data:image/jpeg;base64,"+base64.b64encode(b"JPEGBYTES").decode() in html
    assert "PMC1" in html
    assert str(img) not in html            # self-contained: no raw path leak

def test_unmatched_text_has_no_figref(tmp_path):
    img=tmp_path/"a.jpg"; img.write_bytes(b"x")
    html=render_briefing_html("## Plan\n\nNothing salient.\n",_store(img),embed_fn=lambda t:[[1.0,0.0]],floor=0.2)
    assert "figref" not in html

def test_no_store_renders_shell_with_title(tmp_path):
    schema={"topic":"left MCA thrombectomy","case":{"case_snapshot":{"one_line_thesis":"reperfuse fast"}}}
    html=render_briefing_html("## H\n\nASPECTS.\n",[],schema=schema,embed_fn=None)
    assert "figref" not in html
    assert "left MCA thrombectomy" in html and "reperfuse fast" in html

def test_table_row_term_not_wrapped():
    md="## T\n\n| Indicator | Source |\n|---|---|\n| ASPECTS | x |\n"
    recs=[FigureRecord("image_bank","1",["aspects"],"cap","",b"\x89PNG\r\n",{"pmcid":"PMC1"},[1.0,0.0])]
    html=render_briefing_html(md,recs,embed_fn=lambda t:[[1.0,0.0]],floor=0.2)
    assert "figref" not in html

def test_textbook_blob_png_mime(tmp_path):
    recs=[FigureRecord("textbook","2",["aspects"],"cap","",b"\x89PNG\r\n\x1a\n",{"heading_path":"H"},[1.0,0.0])]
    html=render_briefing_html("## I\n\nASPECTS here.\n",recs,embed_fn=lambda t:[[1.0,0.0]],floor=0.2)
    assert "data:image/png;base64," in html
