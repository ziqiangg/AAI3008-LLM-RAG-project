import os
<<<<<<< Updated upstream
=======
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from flask import Blueprint, current_app, jsonify, request, send_file
from sqlalchemy import or_
from werkzeug.utils import secure_filename
>>>>>>> Stashed changes

from app.backend.config import Config
from app.backend.database import get_db_session
from app.backend.models import Document, DocumentChunk
from app.backend.services.injestion import run_ingestion_pipeline

documents_bp = Blueprint("documents", __name__)

<<<<<<< Updated upstream
# ── Existing GET /api/documents/ route (leave as you have it) ──
=======
_INGESTION_STATE: Dict[str, Dict[str, object]] = {}
_INGESTION_STATE_LOCK = threading.Lock()


def _with_no_store(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _allowed_extension(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = {item.lower() for item in (Config.ALLOWED_EXTENSIONS or [])}
    return bool(ext) and (not allowed or ext in allowed)


def _iso_from_timestamp(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).isoformat()


def _snapshot_ingestion_state(filename: str) -> Optional[Dict[str, object]]:
    with _INGESTION_STATE_LOCK:
        state = _INGESTION_STATE.get(filename)
        return dict(state) if state else None


def _upsert_ingestion_state(filename: str, **changes) -> Dict[str, object]:
    with _INGESTION_STATE_LOCK:
        state = _INGESTION_STATE.setdefault(filename, {})
        state.update(changes)
        state["updated_at"] = time.time()
        return dict(state)


def _clear_ingestion_state(filename: str) -> None:
    with _INGESTION_STATE_LOCK:
        _INGESTION_STATE.pop(filename, None)


def _estimated_progress(state: Optional[Dict[str, object]]) -> int:
    if not state:
        return 0

    status = state.get("status")
    if status == "failed":
        return 100
    if status == "queued":
        return max(5, int(state.get("progress") or 5))
    if status != "processing":
        return max(0, min(100, int(state.get("progress") or 0)))

    base = max(12, int(state.get("progress") or 12))
    started_at = state.get("started_at")
    if isinstance(started_at, (int, float)):
        elapsed = max(0.0, time.time() - started_at)
        ramp = min(78, int((elapsed / 240.0) * 78))
        return min(95, max(base, 12 + ramp))
    return min(95, base)


def _serialize_processing_doc(
    *,
    filename: str,
    file_path: str,
    file_type: Optional[str],
    upload_date: Optional[str],
    state: Optional[Dict[str, object]],
) -> Dict[str, object]:
    state = state or {}
    status = state.get("status") or "queued"
    progress = _estimated_progress(state)
    subjects = state.get("subjects") or state.get("subject") or []
    if isinstance(subjects, str):
        subjects = [subjects]
    is_indexed = status == "indexed" and state.get("document_id") is not None

    if status == "failed":
        status_message = state.get("error_message") or "Processing failed"
    elif status == "queued":
        status_message = state.get("status_message") or "Queued for processing"
    else:
        status_message = state.get("status_message") or f"Processing {progress}%"

    return {
        "id": state.get("document_id"),
        "user_id": state.get("user_id"),
        "folder_id": state.get("folder_id"),
        "filename": filename,
        "file_path": file_path,
        "file_type": file_type,
        "title": None,
        "subject": subjects,
        "upload_date": upload_date,
        "chunk_count": int(state.get("chunk_count") or 0),
        "is_file_only": not is_indexed,
        "is_pending": status in {"queued", "processing"},
        "status": status,
        "status_message": status_message,
        "progress": progress,
        "error_message": state.get("error_message"),
    }


def _decorate_indexed_document(doc: Dict[str, object]) -> Dict[str, object]:
    doc["is_file_only"] = False
    doc["is_pending"] = False
    doc["status"] = "indexed"
    doc["progress"] = 100
    doc["error_message"] = None
    return doc

def _scan_upload_folder():
    upload_dir = Config.UPLOAD_FOLDER
    if not upload_dir:
        return []

    os.makedirs(upload_dir, exist_ok=True)
    if not os.path.isdir(upload_dir):
        return []

    try:
        entries = list(os.scandir(upload_dir))
    except OSError:
        return []

    uploads = []
    for entry in entries:
        if not entry.is_file():
            continue
        if not _allowed_extension(entry.name):
            continue

        try:
            stat = entry.stat()
            modified_at = stat.st_mtime
        except OSError:
            modified_at = None

        uploads.append({
            "filename": entry.name,
            "file_path": os.path.abspath(entry.path),
            "file_type": entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else None,
            "upload_date": _iso_from_timestamp(modified_at),
        })

    uploads.sort(key=lambda item: item.get("upload_date") or "", reverse=True)
    return uploads


def _resolve_document_file_path(file_path: Optional[str], filename: Optional[str]) -> Optional[str]:
    candidates = []

    def add_candidate(path: Optional[str]) -> None:
        if not path or not isinstance(path, str):
            return
        normalized = os.path.abspath(path)
        if normalized not in candidates:
            candidates.append(normalized)

    add_candidate(file_path)

    if file_path:
        add_candidate(os.path.join(Config.UPLOAD_FOLDER, os.path.basename(file_path)))

    if filename:
        safe_name = secure_filename(filename)
        if safe_name:
            add_candidate(os.path.join(Config.UPLOAD_FOLDER, safe_name))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return None


def _should_include_for_user(document_user_id: Optional[int], requested_user_id: Optional[int]) -> bool:
    if requested_user_id is None:
        return True
    return document_user_id in {None, requested_user_id}


def _process_file_in_background(
    app,
    *,
    file_path: str,
    filename: str,
    user_id: Optional[int],
    folder_id: Optional[int],
    subject: str,
) -> None:
    _upsert_ingestion_state(
        filename,
        status="processing",
        status_message="Indexing for retrieval",
        progress=15,
        started_at=time.time(),
        error_message=None,
    )

    def update_progress(*, progress: Optional[int] = None, status_message: Optional[str] = None, **details) -> None:
        changes = {key: value for key, value in details.items() if value is not None}
        if progress is not None:
            changes["progress"] = progress
        if status_message:
            changes["status_message"] = status_message
        if changes:
            _upsert_ingestion_state(filename, **changes)

    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found on disk: {filename}")

        indexed_payload = None
        with app.app_context():
            with get_db_session() as session:
                doc = run_ingestion_pipeline(
                    db_session=session,
                    file_path=file_path,
                    user_id=user_id,
                    subject=subject,
                    progress_callback=update_progress,
                )
                if folder_id is not None:
                    doc.folder_id = folder_id
                session.flush()
                indexed_payload = {
                    "document_id": doc.id,
                    "user_id": doc.user_id,
                    "folder_id": doc.folder_id,
                    "file_path": doc.file_path,
                    "file_type": doc.file_type,
                    "upload_date": doc.upload_date.isoformat() if doc.upload_date else None,
                    "subjects": list(doc.subject or []),
                    "chunk_count": int(doc.chunk_count or 0),
                }

        _upsert_ingestion_state(
            filename,
            status="indexed",
            status_message="Indexed and ready",
            progress=100,
            error_message=None,
            completed_at=time.time(),
            **(indexed_payload or {}),
        )
        app.logger.info("Background ingestion completed for %s", filename)
    except ValueError as exc:
        app.logger.error("Ingestion error for %s: %s", filename, exc)
        _upsert_ingestion_state(
            filename,
            status="failed",
            status_message="Processing failed",
            progress=100,
            error_message=str(exc),
        )
    except Exception:
        app.logger.exception("Unexpected ingestion error for %s", filename)
        _upsert_ingestion_state(
            filename,
            status="failed",
            status_message="Processing failed",
            progress=100,
            error_message="Ingestion failed. See server logs.",
        )

def _queue_background_ingestion(
    app,
    *,
    file_path: str,
    user_id: Optional[int],
    folder_id: Optional[int],
    subject: str,
) -> Dict[str, object]:
    filename = os.path.basename(file_path)
    current_state = _snapshot_ingestion_state(filename)
    if current_state and current_state.get("status") in {"queued", "processing"}:
        updates = {}
        if current_state.get("user_id") is None and user_id is not None:
            updates["user_id"] = user_id
        if current_state.get("folder_id") is None and folder_id is not None:
            updates["folder_id"] = folder_id
        if updates:
            current_state = _upsert_ingestion_state(filename, **updates)
        return current_state

    state = _upsert_ingestion_state(
        filename,
        status="queued",
        status_message="Queued for processing",
        progress=5,
        user_id=user_id,
        folder_id=folder_id,
        file_path=os.path.abspath(file_path),
        file_type=filename.rsplit(".", 1)[-1].lower() if "." in filename else None,
        upload_date=_iso_from_timestamp(os.path.getmtime(file_path)) if os.path.exists(file_path) else None,
        error_message=None,
        queued_at=time.time(),
        started_at=None,
    )

    worker = threading.Thread(
        target=_process_file_in_background,
        kwargs={
            "app": app,
            "file_path": file_path,
            "filename": filename,
            "user_id": user_id,
            "folder_id": folder_id,
            "subject": subject or "General",
        },
        daemon=True,
    )
    worker.start()
    return state


>>>>>>> Stashed changes
@documents_bp.route("/", methods=["GET"])
def get_documents():
    user_id = request.args.get("user_id", type=int)

    with get_db_session() as session:
        query = session.query(Document)
        if user_id is not None:
<<<<<<< Updated upstream
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
=======
            query = query.filter(or_(Document.user_id == user_id, Document.user_id.is_(None)))

        docs = query.order_by(Document.upload_date.desc()).all()
        serialized_docs = [doc.to_dict() for doc in docs]

    for doc in serialized_docs:
        _decorate_indexed_document(doc)

    existing_filenames = {doc.get("filename") for doc in serialized_docs if doc.get("filename")}
    app = current_app._get_current_object()
    synthetic_docs = []

    for upload in _scan_upload_folder():
        filename = upload["filename"]
        if filename in existing_filenames:
            _clear_ingestion_state(filename)
            continue

        state = _snapshot_ingestion_state(filename)
        if not state or state.get("status") not in {"queued", "processing", "failed", "indexed"}:
            state = _queue_background_ingestion(
                app,
                file_path=upload["file_path"],
                user_id=None,
                folder_id=None,
                subject="General",
            )

        if not _should_include_for_user(state.get("user_id"), user_id):
            continue

        synthetic_docs.append(
            _serialize_processing_doc(
                filename=filename,
                file_path=upload["file_path"],
                file_type=upload["file_type"],
                upload_date=upload["upload_date"],
                state=state,
            )
        )

    all_documents = serialized_docs + synthetic_docs
    all_documents.sort(key=lambda doc: doc.get("upload_date") or "", reverse=True)
    return _with_no_store(jsonify({"documents": all_documents})), 200


@documents_bp.route("/status/<path:filename>", methods=["GET"])
def get_document_status(filename: str):
    user_id = request.args.get("user_id", type=int)
    safe_name = secure_filename(os.path.basename(filename or ""))
    if not safe_name:
        return jsonify({"error": "Filename is required"}), 400

    state = _snapshot_ingestion_state(safe_name)
    if state:
        state_file_path = state.get("file_path") if isinstance(state.get("file_path"), str) else None
        resolved_file_path = state_file_path or _resolve_document_file_path(
            os.path.join(Config.UPLOAD_FOLDER, safe_name),
            safe_name,
        )
        document = _serialize_processing_doc(
            filename=safe_name,
            file_path=resolved_file_path or os.path.join(Config.UPLOAD_FOLDER, safe_name),
            file_type=state.get("file_type") if isinstance(state.get("file_type"), str) else None,
            upload_date=state.get("upload_date") if isinstance(state.get("upload_date"), str) else None,
            state=state,
        )
        return _with_no_store(jsonify({"document": document})), 200

    with get_db_session() as session:
        query = session.query(Document).filter(Document.filename == safe_name)
        if user_id is not None:
            query = query.filter(or_(Document.user_id == user_id, Document.user_id.is_(None)))

        doc = query.order_by(Document.upload_date.desc()).first()
        if doc:
            return _with_no_store(jsonify({"document": _decorate_indexed_document(doc.to_dict())})), 200

    file_path = _resolve_document_file_path(
        os.path.join(Config.UPLOAD_FOLDER, safe_name),
        safe_name,
    )
    if not file_path:
        return jsonify({"error": f"Document status for {safe_name} not found"}), 404

    state = _queue_background_ingestion(
        current_app._get_current_object(),
        file_path=file_path,
        user_id=user_id,
        folder_id=None,
        subject="General",
    )
    document = _serialize_processing_doc(
        filename=safe_name,
        file_path=file_path,
        file_type=safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else None,
        upload_date=_iso_from_timestamp(os.path.getmtime(file_path)) if os.path.exists(file_path) else None,
        state=state,
    )
    return _with_no_store(jsonify({"document": document})), 200

@documents_bp.route("/upload", methods=["POST"])
def upload_document():
>>>>>>> Stashed changes
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in Config.ALLOWED_EXTENSIONS:
        return jsonify({
            "error": f"File type not allowed. Supported types: {Config.ALLOWED_EXTENSIONS}"
        }), 415

    subject = request.form.get("subject", "General")
    user_id = request.form.get("user_id", type=int)
<<<<<<< Updated upstream
=======
    folder_id = request.form.get("folder_id", type=int)
>>>>>>> Stashed changes

    filename = secure_filename(file.filename)
    upload_dir = Config.UPLOAD_FOLDER
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)
    current_app.logger.info("Saved upload to %s", file_path)

    state = _queue_background_ingestion(
        current_app._get_current_object(),
        file_path=file_path,
        user_id=user_id,
        folder_id=folder_id,
        subject=subject,
    )

    document = _serialize_processing_doc(
        filename=filename,
        file_path=os.path.abspath(file_path),
        file_type=ext or None,
        upload_date=_iso_from_timestamp(os.path.getmtime(file_path)),
        state=state,
    )

    return jsonify({
        "message": "Document uploaded. Processing started.",
        "document": document,
    }), 202

<<<<<<< Updated upstream
    try:
        with get_db_session() as session:
            doc = run_ingestion_pipeline(
                db_session=session,
                file_path=file_path,
                user_id=user_id,
                subject=subject,
            )
            # run_ingestion_pipeline commits internally; we just return the doc
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
=======

>>>>>>> Stashed changes
@documents_bp.route("/<int:doc_id>", methods=["DELETE"])
def delete_document(doc_id: int):
    with get_db_session() as session:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return jsonify({"error": f"Document {doc_id} not found"}), 404

        file_path = doc.file_path
        session.delete(doc)

    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            current_app.logger.warning("Failed to delete file %s", file_path)

    return jsonify({"message": f"Document {doc_id} and its chunks deleted."}), 200


<<<<<<< Updated upstream
# ── GET /api/documents/<id> ─────────────────────────────
=======
>>>>>>> Stashed changes
@documents_bp.route("/<int:doc_id>", methods=["GET"])
def get_document_chunks(doc_id: int):
    limit = request.args.get("limit", type=int, default=100)

    with get_db_session() as session:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return jsonify({"error": f"Document {doc_id} not found"}), 404

        chunks = (
            session.query(DocumentChunk)
            .filter_by(document_id=doc_id)
            .order_by(DocumentChunk.chunk_order)
            .limit(limit)
            .all()
        )

        chunks_data = []
        for chunk in chunks:
            chunks_data.append({
                "chunk_id": chunk.id,
                "chunk_order": chunk.chunk_order,
                "content": chunk.content,
                "len": len(chunk.content) if chunk.content else 0,
                "metadata": chunk.chunk_metadata or {},
            })

        filename = doc.filename

    return _with_no_store(jsonify({
        "document_id": doc_id,
        "filename": filename,
        "chunks": chunks_data,
    })), 200


<<<<<<< Updated upstream
# ── PATCH /api/documents/<id> ─────────────────────────────
@documents_bp.route("/<int:doc_id>", methods=["PATCH"])
def update_document(doc_id: int):
    """
    Update document metadata (e.g., subject).
    Allows users to manually correct auto-classified subjects.
    """
=======
@documents_bp.route("/raw/<int:doc_id>", methods=["GET", "HEAD"])
def get_document_file(doc_id: int):
>>>>>>> Stashed changes
    with get_db_session() as session:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return jsonify({"error": f"Document {doc_id} not found"}), 404
<<<<<<< Updated upstream
        
        data = request.get_json()
        
        if 'subject' in data:
            new_subject = data['subject']
            
            # Support both single subject and array
=======

        file_path = _resolve_document_file_path(doc.file_path, doc.filename)
        download_name = doc.filename or (os.path.basename(file_path) if file_path else None)

    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "Uploaded file is not available on disk"}), 404

    return send_file(file_path, as_attachment=False, download_name=download_name or os.path.basename(file_path))


@documents_bp.route("/raw-by-name/<path:filename>", methods=["GET", "HEAD"])
def get_document_file_by_name(filename: str):
    safe_name = secure_filename(os.path.basename(filename or ""))
    if not safe_name:
        return jsonify({"error": "Filename is required"}), 400

    file_path = _resolve_document_file_path(
        os.path.join(Config.UPLOAD_FOLDER, safe_name),
        safe_name,
    )
    if not file_path:
        return jsonify({"error": "Uploaded file is not available on disk"}), 404

    return send_file(file_path, as_attachment=False, download_name=safe_name)


@documents_bp.route("/<int:doc_id>", methods=["PATCH"])
def update_document(doc_id: int):
    with get_db_session() as session:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return jsonify({"error": f"Document {doc_id} not found"}), 404

        data = request.get_json() or {}

        if "folder_id" in data:
            doc.folder_id = data["folder_id"]

        if "subject" in data:
            new_subject = data["subject"]
>>>>>>> Stashed changes
            if isinstance(new_subject, str):
                new_subject = [new_subject]

            invalid_subjects = [item for item in new_subject if item not in Config.VALID_SUBJECTS]
            if invalid_subjects:
                return jsonify({
                    "error": f"Invalid subject(s): {', '.join(invalid_subjects)}",
                    "valid_subjects": Config.VALID_SUBJECTS,
                }), 400

            doc.subject = new_subject
            current_app.logger.info("Updated document %s subjects to %s", doc_id, new_subject)

        return jsonify({
            "message": "Document updated successfully",
<<<<<<< Updated upstream
            "document": doc.to_dict()
        }), 200
=======
            "document": doc.to_dict(),
        }), 200

>>>>>>> Stashed changes
