from engine.ingestion.types import SourceBlock

STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"]
TEXT_TAGS = ["h1", "h2", "h3", "p", "li"]


def extract_from_html(html: str, url: str) -> tuple[list[SourceBlock], str]:
    """BeautifulSoup fallback used when Docling cannot handle the page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(STRIP_TAGS):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else url
    main = soup.find("article") or soup.find("main") or soup.body or soup

    blocks: list[SourceBlock] = []
    for index, element in enumerate(main.find_all(TEXT_TAGS), start=1):
        text = element.get_text(" ", strip=True)
        if len(text) < 3:
            continue
        kind = "heading" if element.name in ("h1", "h2", "h3") else "paragraph"
        heading = text if kind == "heading" else None
        blocks.append(SourceBlock(text=text, ref=f"{url} \u00a7{index}", kind=kind, heading=heading))

    if not blocks:
        fallback = main.get_text(" ", strip=True)
        if fallback:
            blocks.append(SourceBlock(text=fallback, ref=f"{url} \u00a71", kind="paragraph"))

    return blocks, title


def _extract_with_docling(html: str, url: str) -> tuple[list[SourceBlock], str]:
    """Primary path: reuse the same Docling pipeline as every other document.

    Docling reconstructs reading order and drops theme chrome far better than
    tag-based scraping, and keeps tables intact.
    """
    from engine.ingestion import documents

    blocks, meta = documents.parse_document(
        html.encode("utf-8", errors="replace"),
        None,
        "page.html",
        url,
    )
    meta.pop("figures", None)

    kept = [b for b in blocks if len((b.text or "").strip()) >= 3]
    title = next((b.text for b in kept if b.kind == "heading"), url)
    return kept, title


def fetch_url(url: str, timeout: float = 20.0) -> tuple[list[SourceBlock], str]:
    import httpx

    headers = {"User-Agent": "ContentTransformationEngine/0.1 (+hackathon)"}
    response = httpx.get(url, timeout=timeout, follow_redirects=True, headers=headers)
    response.raise_for_status()

    try:
        return _extract_with_docling(response.text, url)
    except Exception:
        return extract_from_html(response.text, url)
