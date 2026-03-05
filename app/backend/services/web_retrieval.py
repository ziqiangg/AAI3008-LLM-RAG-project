import re
import requests
from urllib.parse import urlparse
import logging
from app.backend.config import Config

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None


def user_explicitly_requested_web(question: str) -> bool:
    q = (question or "").lower()
    return any(k in q for k in Config.WEB_EXPLICIT_KEYWORDS)


def is_trusted_url(url: str) -> bool:
    try:
        u = urlparse(url)
        if Config.WEB_REQUIRE_HTTPS and u.scheme != "https":
            return False
        host = (u.hostname or "").lower()
        # allow exact domain OR subdomain of allowed domain
        for d in Config.WEB_TRUSTED_DOMAINS:
            d = d.lower()
            if host == d or host.endswith("." + d):
                return True
        return False
    except Exception:
        return False


def _extract_text(html: str) -> str:
    if not html:
        return ""
    if BeautifulSoup is None:
        # fallback: strip tags very roughly
        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    soup = BeautifulSoup(html, "html.parser")
    # remove scripts/styles
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_page_text(url: str) -> str:
    url = normalize_url(url)
    if not is_trusted_url(url):
        return ""
    
    resp = requests.get(
        url,
        timeout=Config.WEB_TIMEOUT_S,
        headers={"User-Agent": "Mozilla/5.0 (RAG-WebFetch)"},
        allow_redirects=True,
    )

    final_url = resp.url
    if not is_trusted_url(final_url):
        return ""

    text = _extract_text(resp.text)
    if len(text) > Config.WEB_MAX_CHARS_PER_PAGE:
        text = text[: Config.WEB_MAX_CHARS_PER_PAGE]
    return text


def serper_search(query: str):
    if not Config.SERPER_API_KEY:
        return []

    payload = {"q": query, "num": Config.WEB_MAX_RESULTS}
    headers = {
        "X-API-KEY": Config.SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    r = requests.post(Config.SERPER_ENDPOINT, json=payload, headers=headers, timeout=Config.WEB_TIMEOUT_S)
    r.raise_for_status()
    data = r.json()
    results = []
    for item in (data.get("organic") or [])[: Config.WEB_MAX_RESULTS]:
        url = normalize_url(item.get("link") or "")
        if not url or not is_trusted_url(url):
            continue
        results.append({
            "title": item.get("title") or urlparse(url).hostname or "Web Source",
            "url": url,
            "snippet": item.get("snippet") or "",
        })
    return results


def web_retrieve_as_chunks(question: str) -> list[dict]:
    results = serper_search(question)
    chunks = []

    for idx, r in enumerate(results, start=1):
        url = r["url"]
        text = fetch_page_text(url)
        if not text:
            continue

        domain = urlparse(url).hostname or "web"
        chunks.append({
            "chunk_id": f"web:{idx}",
            "document_id": None,
            "filename": domain,
            "content": text,
            "chunk_order": idx,
            "metadata": {
                "source_type": "web",
                "url": url,
                "title": r.get("title"),
                "snippet": r.get("snippet"),
            },
            "similarity": 0.0,
        })

    return chunks

def normalize_url(url: str) -> str:
    try:
        u = urlparse(url)
        if u.scheme == "http":
            return url.replace("http://", "https://", 1)
        return url
    except Exception:
        return url