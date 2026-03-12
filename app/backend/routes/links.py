import logging
from urllib.parse import urlparse

from flask import Blueprint, request, jsonify
from app.backend.database import get_db_session
from app.backend.models import Document
from app.backend.config import Config
from app.backend.services.injestion import chunk_sections_to_db
from app.backend.services.web_link_ingest import (
    is_trusted_url,
    fetch_page_html,
    extract_html_sections,
)

links_bp = Blueprint("links", __name__)
logger = logging.getLogger(__name__)

@links_bp.route("/ingest", methods=["POST"])
def ingest_links():
    data = request.get_json(silent=True) or {}
    urls = data.get("urls") or []
    user_id = data.get("user_id")
    folder_id = data.get("folder_id")  # NEW: optional folder assignment

    if not isinstance(urls, list) or not urls:
        return jsonify({"error": "urls must be a non-empty list"}), 400
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    ingested = []
    rejected = []

    with get_db_session() as db:
        for url in urls:
            url = (url or "").strip()
            if not url:
                continue

            if not is_trusted_url(url):
                rejected.append({"url": url, "reason": "untrusted_or_invalid"})
                continue

            html = fetch_page_html(url)
            if not html:
                rejected.append({"url": url, "reason": "fetch_failed"})
                continue

            sections = extract_html_sections(html)
            if not sections:
                rejected.append({"url": url, "reason": "no_sections_extracted"})
                continue
            
            domain = urlparse(url).hostname or "link"
            title = domain
            filename = f"LINK: {domain} - {title}"

            doc = Document(
                user_id=int(user_id),
                folder_id=int(folder_id) if folder_id else None,  # NEW: assign to folder
                filename=filename,
                file_path=url,     # store URL here
                file_type="link",
                title=title,
                subject=["General"]
            )
            db.add(doc)
            db.flush()  # ensures doc.id exists

            chunk_count, doc_subject_results = chunk_sections_to_db(
                db_session=db,
                document_id=doc.id,
                sections=sections,
                source_metadata={"source_type": "link", "url": url},
            )
            doc.chunk_count = chunk_count

            # ✅ set document tags for sidebar
            doc.subject = [s["name"] for s in (doc_subject_results or [])][:2] or ["General"]
            ingested.append({"document_id": doc.id, "url": url, "chunks": chunk_count})

        db.commit()

    return jsonify({"ingested": ingested, "rejected": rejected}), 200