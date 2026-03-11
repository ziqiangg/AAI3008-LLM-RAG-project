from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os

from app.backend.models import Document, DocumentChunk
from app.backend.database import get_db_session
from app.backend.config import Config
from app.backend.services.injestion import run_ingestion_pipeline  # adjust path if needed

documents_bp = Blueprint("documents", __name__)

# ── Existing GET /api/documents/ route (leave as you have it) ──
@documents_bp.route("/", methods=["GET"])
def get_documents():
    user_id = request.args.get("user_id", type=int)
    with get_db_session() as session:
        query = session.query(Document)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        docs = query.order_by(Document.upload_date.desc()).all()
        return jsonify({"documents": [d.to_dict() for d in docs]}), 200


# ── POST /api/documents/upload ─────────────────────────────
@documents_bp.route("/upload", methods=["POST"])
def upload_document():
    """
    Accept a file upload, save it to UPLOAD_FOLDER,
    then run the LangChain ingestion pipeline:
    Load → Split → Embed → Store (Document + DocumentChunk).
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in Config.ALLOWED_EXTENSIONS:
        return jsonify({
            "error": f"File type not allowed. Supported types: {Config.ALLOWED_EXTENSIONS}"
        }), 415

    subject = request.form.get("subject", "General")
    user_id = request.form.get("user_id", type=int)
    folder_id = request.form.get("folder_id", type=int)  # optional folder

    # Save file to disk
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
            # Assign folder if provided
            if folder_id:
                doc.folder_id = folder_id
                session.commit()
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

# ── DELETE /api/documents/<id> ─────────────────────────────
@documents_bp.route("/<int:doc_id>", methods=["DELETE"])
def delete_document(doc_id: int):
    """
    Delete a document and its chunks (via CASCADE), and remove the underlying file.
    """
    with get_db_session() as session:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return jsonify({"error": f"Document {doc_id} not found"}), 404

        file_path = doc.file_path

        # Chunks are deleted automatically via ON DELETE CASCADE
        session.delete(doc)
        # session.commit() is handled by get_db_session context manager

    # Remove file from disk after DB commit
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            current_app.logger.warning(f"Failed to delete file {file_path}")

    return jsonify({"message": f"Document {doc_id} and its chunks deleted."}), 200


# ── GET /api/documents/<id> ─────────────────────────────
@documents_bp.route("/<int:doc_id>", methods=["GET"])
def get_document_chunks(doc_id: int):
    """
    Get chunks for a specific document.
    """
    limit = request.args.get("limit", type=int, default=100)
    
    with get_db_session() as session:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return jsonify({"error": f"Document {doc_id} not found"}), 404
        
        chunks = session.query(DocumentChunk)\
            .filter_by(document_id=doc_id)\
            .order_by(DocumentChunk.chunk_order)\
            .limit(limit)\
            .all()
        
        chunks_data = []
        for chunk in chunks:
            chunk_dict = {
                'chunk_id': chunk.id,
                'chunk_order': chunk.chunk_order,
                'content': chunk.content,
                'len': len(chunk.content) if chunk.content else 0,
                'metadata': chunk.chunk_metadata or {}
            }
            chunks_data.append(chunk_dict)
        
        return jsonify({
            'document_id': doc_id,
            'filename': doc.filename,
            'chunks': chunks_data
        }), 200


# ── PATCH /api/documents/<id> ─────────────────────────────
@documents_bp.route("/<int:doc_id>", methods=["PATCH"])
def update_document(doc_id: int):
    """
    Update document metadata (e.g., subject).
    Allows users to manually correct auto-classified subjects.
    """
    with get_db_session() as session:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return jsonify({"error": f"Document {doc_id} not found"}), 404
        
        data = request.get_json()
        
        if 'subject' in data:
            new_subject = data['subject']
            
            # Support both single subject and array
            if isinstance(new_subject, str):
                new_subject = [new_subject]
            
            # Validate subjects
            invalid_subjects = [s for s in new_subject if s not in Config.VALID_SUBJECTS]
            if invalid_subjects:
                return jsonify({
                    "error": f"Invalid subject(s): {', '.join(invalid_subjects)}",
                    "valid_subjects": Config.VALID_SUBJECTS
                }), 400
            
            doc.subject = new_subject
            current_app.logger.info(f"Updated document {doc_id} subjects to: {new_subject}")

        if 'folder_id' in data:
            doc.folder_id = data['folder_id']  # can be None (unassign) or int
        
        return jsonify({
            "message": "Document updated successfully",
            "document": doc.to_dict()
        }), 200