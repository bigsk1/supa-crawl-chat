import base64

from content_hygiene import clean_crawled_content


def test_clean_crawled_content_removes_base64_data_uri():
    payload = base64.b64encode(b"hello" * 300).decode("ascii")
    raw = f"# Title\n\nUseful docs text.\n\n![image](data:image/png;base64,{payload})"

    result = clean_crawled_content(raw)

    assert "Useful docs text" in result["content"]
    assert payload not in result["content"]
    assert result["metadata"]["removed_data_uri_count"] == 1
    assert "encoded_noise_removed" in result["metadata"]["quality_flags"]


def test_clean_crawled_content_removes_encoded_fenced_block_but_keeps_code():
    encoded = "A" * 800
    raw = (
        "Before\n\n"
        "```python\nprint('keep me')\n```\n\n"
        f"```text\n{encoded}\n```\n\n"
        "After"
    )

    result = clean_crawled_content(raw)

    assert "print('keep me')" in result["content"]
    assert encoded not in result["content"]
    assert result["metadata"]["removed_encoded_fence_count"] == 1

