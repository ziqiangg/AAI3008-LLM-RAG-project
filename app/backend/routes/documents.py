from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os

from app.backend.models import Document, DocumentChunk
from app.backend.database import get_db_session
from app.backend.config import Config
from app.backend.services.injestion import run_ingestion_pipeline  # adjust path if needed

documents_bp = Blueprint("documents", __name__)

# ── GET /api/documents/ ─────────────────────────────
@documents_bp.route("/", methods=["GET"])
def get_documents():
    user_id = request.args.get("user_id", type=int)

    with get_db_session() as session:
        query = session.query(Document)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)

        docs = query.order_by(Document.upload_date.desc()).all()
        return jsonify({"documents": [d.to_dict() for d in docs]}), 200


# ── POST /api/documents/upload ─────────────────────
@documents_bp.route("/upload", methods=["POST"])
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in Config.ALLOWED_EXTENSIONS:
        return jsonify({"error": f"File type not allowed. Supported types: {Config.ALLOWED_EXTENSIONS}"}), 415

    subject = request.form.get("subject", "General")
    user_id = request.form.get("user_id", type=int)

    filename = secure_filename(file.filename)
    upload_dir = Config.UPLOAD_FOLDER
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)
    current_app.logger.info(f"Saved upload to {file_path}")

    try:
        with get_db_session() as session:
            doc = run_ingestion_pipeline(
                db_session=session,
                file_path=file_path,
                user_id=user_id,
                subject=subject,
            )
            return jsonify({
                "message": "Document uploaded and ingested successfully.",
                "document": doc.to_dict(),
            }), 201

    except ValueError as e:
        current_app.logger.error(f"Ingestion error for {filename}: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Ingestion error for {filename}: {e}")
        return jsonify({"error": "Ingestion failed. See server logs."}), 500


# ── GET/DELETE /api/documents/<id> ──────────────────
@documents_bp.route("/<int:doc_id>", methods=["GET", "DELETE"])
def get_or_delete_document(doc_id: int):
    with get_db_session() as session:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return jsonify({"error": f"Document {doc_id} not found"}), 404

        # ---------- GET (return segmented chunks) ----------
        if request.method == "GET":
            limit = request.args.get("limit", default=200, type=int)

            chunks = (
                session.query(DocumentChunk)
                .filter_by(document_id=doc_id)
                .order_by(DocumentChunk.chunk_order.asc())
                .limit(limit)
                .all()
            )

            return jsonify({
                "id": doc.id,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "subject": doc.subject,
                "upload_date": doc.upload_date.isoformat() if doc.upload_date else None,
                "count": len(chunks),
                "chunks": [
                    {
                        "chunk_order": c.chunk_order,
                        "content": c.content or "",
                        "len": len(c.content or ""),
                        "metadata": c.chunk_metadata,
                    }
                    for c in chunks
                ]
            }), 200

        # ---------- DELETE ----------
        file_path = doc.file_path
        session.query(DocumentChunk).filter_by(document_id=doc_id).delete()
        session.delete(doc)
        # commit handled by get_db_session context manager

    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            current_app.logger.warning(f"Failed to delete file {file_path}")

    return jsonify({"message": f"Document {doc_id} and its chunks deleted."}), 200


# ── GET /api/documents/<id>/chunks (optional inspector endpoint) ──
@documents_bp.route("/<int:doc_id>/chunks", methods=["GET"])
def get_document_chunks(doc_id: int):
    limit = request.args.get("limit", default=50, type=int)

    with get_db_session() as session:
        chunks = (
            session.query(DocumentChunk)
            .filter_by(document_id=doc_id)
            .order_by(DocumentChunk.chunk_order.asc())
            .limit(limit)
            .all()
        )

        return jsonify({
            "document_id": doc_id,
            "count": len(chunks),
            "chunks": [
                {
                    "chunk_order": c.chunk_order,
                    "len": len(c.content or ""),
                    "preview": (c.content or "")[:160],
                    "content": c.content or "",
                    "metadata": c.chunk_metadata,
                }
                for c in chunks
            ]
        }), 200