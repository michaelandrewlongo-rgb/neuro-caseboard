from dataclasses import dataclass, field

from .config import load_config
from .embed import Embedder
from .index import Index
from .rerank import Reranker
from .synthesize import synthesize


@dataclass
class QueryResult:
    answer: str
    citations: list = field(default_factory=list)


class Engine:
    def __init__(self, config, embedder, index, reranker, client,
                 synth_fn=synthesize):
        self.config = config
        self.embedder = embedder
        self.index = index
        self.reranker = reranker
        self.client = client
        self.synth_fn = synth_fn

    def query(self, question):
        qv = self.embedder.embed_query(question)
        hits = self.index.hybrid_search(question, qv, self.config.retrieve_k)
        top = self.reranker.rerank(question, hits, self.config.rerank_k)
        syn = self.synth_fn(question, top, self.client,
                            self.config.openrouter_model)
        return QueryResult(answer=syn.answer, citations=syn.citations)


_engine = None


def get_engine(config=None):
    global _engine
    if _engine is not None:
        return _engine
    config = config or load_config()
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=config.openrouter_api_key)
    embedder = Embedder(config.embed_model, device=config.embed_device)
    index = Index(config.index_dir)
    reranker = Reranker(config.rerank_model, device=config.embed_device)
    _engine = Engine(config, embedder, index, reranker, client)
    return _engine


def query(question, config=None):
    return get_engine(config).query(question)
