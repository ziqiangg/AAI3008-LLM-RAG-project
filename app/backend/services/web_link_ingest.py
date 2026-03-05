import re
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from app.backend.config import Config


def is_trusted_url(url: str) -> bool:
    try:
        u = urlparse(url)
        if Config.WEB_REQUIRE_HTTPS and u.scheme != "https":
            return False
        host = (u.hostname or "").lower()
        if not host:
            return False
        for d in Config.WEB_TRUSTED_DOMAINS:
            d = d.lower()
            if host == d or host.endswith("." + d):
                return True
        return False
    except Exception:
        return False


def fetch_page_html(url: str) -> str:
    if not is_trusted_url(url):
        return ""

    r = requests.get(
        url,
        timeout=Config.WEB_TIMEOUT_S,
        headers={"User-Agent": "Mozilla/5.0 (LinkIngest)"},
        allow_redirects=True,
    )
    if not is_trusted_url(r.url):
        return ""
    return r.text or ""


def extract_html_sections(html: str) -> list[dict]:
    """
    Hybrid: split by headings (h1/h2/h3) inside <main>/<article>,
    drop nav/header/footer/aside to reduce boilerplate.
    Returns: [{"title": "...", "text": "..."}]
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup.body or soup

    # remove typical chrome
    for tag in root.find_all(["nav", "header", "footer", "aside"]):
        tag.decompose()

    sections = []
    cur_title = "Intro"
    cur_lines: list[str] = []

    def flush():
        nonlocal cur_title, cur_lines
        text = "\n".join([ln.strip() for ln in cur_lines if ln.strip()])
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text and len(text) >= 200:
            sections.append({"title": cur_title[:120], "text": text})
        cur_lines = []

    for el in root.find_all(["h1", "h2", "h3", "p", "li"]):
        if el.name in ("h1", "h2", "h3"):
            flush()
            cur_title = el.get_text(" ", strip=True) or "Section"
        else:
            t = el.get_text(" ", strip=True)
            if t:
                cur_lines.append(t)

    flush()

    # final cleanup pass for common boilerplate lines
    bad_prefixes = (
        "skip to main content", "cookie preferences", "privacy", "site terms",
        "all rights reserved", "©", "sign in", "create account", "contact us",
    )
    cleaned = []
    for s in sections:
        lines = [ln.strip() for ln in s["text"].split("\n") if ln.strip()]
        lines = [ln for ln in lines if not any(ln.lower().startswith(p) for p in bad_prefixes)]
        txt = "\n".join(lines).strip()
        if txt:
            cleaned.append({"title": s["title"], "text": txt})

    return cleaned