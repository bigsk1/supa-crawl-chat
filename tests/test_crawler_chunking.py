from crawler import WebCrawler


class _Tokenizer:
    def encode(self, text):
        return text.split()

    def decode(self, tokens):
        return " ".join(tokens)


class _EmbeddingStub:
    tokenizer = _Tokenizer()

    def count_tokens(self, text):
        return len(text.split())


def _crawler_without_services():
    crawler = WebCrawler.__new__(WebCrawler)
    crawler.embedding_generator = _EmbeddingStub()
    return crawler


def test_small_page_is_not_duplicated_as_chunk():
    crawler = _crawler_without_services()
    page = {
        "url": "https://example.com/docs",
        "title": "Docs",
        "content": "short page content",
        "metadata": {},
    }

    pages = crawler.chunk_content(page, max_tokens=20, overlap_tokens=2)

    assert len(pages) == 1
    assert pages[0]["is_chunk"] is False
    assert pages[0]["chunk_index"] is None
    assert pages[0]["metadata"]["has_chunks"] is False
    assert pages[0]["metadata"]["chunk_count"] == 0


def test_large_page_returns_parent_plus_non_duplicate_chunks():
    crawler = _crawler_without_services()
    content = " ".join(f"word{i}" for i in range(14))
    page = {
        "url": "https://example.com/docs",
        "title": "Docs",
        "content": content,
        "metadata": {},
    }

    pages = crawler.chunk_content(page, max_tokens=5, overlap_tokens=1)

    assert pages[0]["is_chunk"] is False
    assert pages[0]["metadata"]["has_chunks"] is True
    assert pages[0]["metadata"]["chunk_count"] == len(pages) - 1
    assert all(chunk["is_chunk"] for chunk in pages[1:])
    assert all(chunk["content"] != content for chunk in pages[1:])
