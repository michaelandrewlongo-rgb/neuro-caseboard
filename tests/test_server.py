from engine.query import QueryResult, Figure
from engine.synthesize import Citation


def test_to_response_maps_fields_and_builds_figure_url():
    from server.schemas import to_response
    result = QueryResult(
        answer="Give nimodipine 60 mg q4h [1].",
        citations=[Citation(n=1, book="Greenberg", chapter="SAH", page=1290)],
        figures=[Figure(source_n=1, book="Rhoton", chapter="", page=212,
                        image_path="/home/u/assets/figures/rhoton_p212.png",
                        caption="Circle of Willis")],
    )
    resp = to_response(result)
    assert resp.answer == "Give nimodipine 60 mg q4h [1]."
    assert resp.citations[0].model_dump() == {
        "n": 1, "book": "Greenberg", "chapter": "SAH", "page": 1290}
    fig = resp.figures[0]
    assert fig.model_dump() == {
        "source_n": 1, "book": "Rhoton", "page": 212,
        "caption": "Circle of Willis", "url": "/figures/rhoton_p212.png"}
