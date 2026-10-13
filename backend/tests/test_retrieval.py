from langchain_core.documents import Document

from app.search.retrieval import dedupe_near_dups, rrf_fuse


def d(url, title="Delivery Boy", emp="Swiggy", loc="Jaya Nagar"):
    return Document(page_content=title, metadata={"url": url, "title": title, "employer": emp, "locality": loc})


def test_rrf_prefers_documents_ranked_well_by_several_queries():
    a, b, c = d("a"), d("b"), d("c")
    fused = rrf_fuse([[a, b], [c, b], [b, a]])
    assert [x.metadata["url"] for x, _ in fused][0] == "b"          # 2nd, 2nd, 1st beats single first places


def test_dedupe_collapses_reposts_but_keeps_distinct_jobs():
    fused = rrf_fuse([[d("1"), d("2"), d("3", emp="Zomato")]])
    unique, removed = dedupe_near_dups(fused)
    assert removed == 1 and {x.metadata["url"] for x, _ in unique} == {"1", "3"}
