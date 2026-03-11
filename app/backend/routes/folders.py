"""
Folder management blueprint → /api/folders/*
<<<<<<< Updated upstream
Users can create folders to organise their uploaded content.
=======
Allows users to create, list, rename, and delete folders for organizing documents.
>>>>>>> Stashed changes
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.backend.database import get_db_session as get_db
from app.backend.models import Folder, Document

folders_bp = Blueprint('folders', __name__)

<<<<<<< Updated upstream
# ── Helper ────────────────────────────────────────────────────────────────────

def _resolve_folder_doc_ids(db, folder_ids, user_id):
    """Return all document IDs that belong to the given folder_ids for this user."""
    docs = (
        db.query(Document.id)
          .join(Folder, Document.folder_id == Folder.id)
          .filter(Folder.id.in_(folder_ids), Folder.user_id == user_id)
          .all()
    )
    return [d.id for d in docs]


# ── CRUD ──────────────────────────────────────────────────────────────────────
=======
>>>>>>> Stashed changes

@folders_bp.route('/', methods=['GET'])
@jwt_required()
def list_folders():
<<<<<<< Updated upstream
=======
    """List all folders for the authenticated user, including document counts."""
>>>>>>> Stashed changes
    user_id = int(get_jwt_identity())
    with get_db() as db:
        folders = (
            db.query(Folder)
<<<<<<< Updated upstream
              .filter_by(user_id=user_id)
              .order_by(Folder.created_at)
              .all()
=======
            .filter_by(user_id=user_id)
            .order_by(Folder.name)
            .all()
>>>>>>> Stashed changes
        )
        return jsonify({'folders': [f.to_dict() for f in folders]}), 200


@folders_bp.route('/', methods=['POST'])
@jwt_required()
def create_folder():
<<<<<<< Updated upstream
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Folder name is required'}), 400

    color = data.get('color', '#6c63ff')

    with get_db() as db:
        folder = Folder(user_id=user_id, name=name, color=color)
=======
    """Create a new folder."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()

    if not name:
        return jsonify({'error': 'Folder name is required'}), 400
    if len(name) > 100:
        return jsonify({'error': 'Folder name must be under 100 characters'}), 400

    with get_db() as db:
        # Check for duplicate names for this user
        existing = db.query(Folder).filter_by(user_id=user_id, name=name).first()
        if existing:
            return jsonify({'error': f'A folder named "{name}" already exists'}), 409

        folder = Folder(user_id=user_id, name=name)
>>>>>>> Stashed changes
        db.add(folder)
        db.commit()
        return jsonify({'folder': folder.to_dict()}), 201


@folders_bp.route('/<int:folder_id>', methods=['PATCH'])
@jwt_required()
<<<<<<< Updated upstream
def update_folder(folder_id):
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
=======
def rename_folder(folder_id):
    """Rename an existing folder."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()

    if not name:
        return jsonify({'error': 'New folder name is required'}), 400

>>>>>>> Stashed changes
    with get_db() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404
<<<<<<< Updated upstream
        if 'name' in data:
            name = data['name'].strip()
            if not name:
                return jsonify({'error': 'Folder name cannot be empty'}), 400
            folder.name = name
        if 'color' in data:
            folder.color = data['color']
=======

        # Check for duplicate names
        dup = db.query(Folder).filter_by(user_id=user_id, name=name).first()
        if dup and dup.id != folder_id:
            return jsonify({'error': f'A folder named "{name}" already exists'}), 409

        folder.name = name
>>>>>>> Stashed changes
        db.commit()
        return jsonify({'folder': folder.to_dict()}), 200


@folders_bp.route('/<int:folder_id>', methods=['DELETE'])
@jwt_required()
def delete_folder(folder_id):
<<<<<<< Updated upstream
    """Delete folder but keep documents (they become unorganised)."""
=======
    """
    Delete a folder. Documents inside are moved to 'unfiled' (folder_id = NULL),
    NOT deleted.
    """
>>>>>>> Stashed changes
    user_id = int(get_jwt_identity())
    with get_db() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404
<<<<<<< Updated upstream
        # Unset folder_id on all docs in this folder
        db.query(Document).filter_by(folder_id=folder_id).update({'folder_id': None})
        db.delete(folder)
        db.commit()
        return jsonify({'message': f'Folder {folder_id} deleted'}), 200


# ── Document assignment ───────────────────────────────────────────────────────

@folders_bp.route('/<int:folder_id>/documents', methods=['GET'])
@jwt_required()
def folder_documents(folder_id):
=======

        # Un-file all documents in this folder instead of deleting them
        db.query(Document).filter_by(folder_id=folder_id).update(
            {'folder_id': None}, synchronize_session='fetch'
        )
        db.delete(folder)
        db.commit()
        return jsonify({'message': f'Folder "{folder.name}" deleted. Documents moved to unfiled.'}), 200


@folders_bp.route('/<int:folder_id>/documents', methods=['GET'])
@jwt_required()
def get_folder_documents(folder_id):
    """Get all documents in a specific folder."""
>>>>>>> Stashed changes
    user_id = int(get_jwt_identity())
    with get_db() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404
<<<<<<< Updated upstream
        docs = db.query(Document).filter_by(folder_id=folder_id, user_id=user_id).all()
        return jsonify({'documents': [d.to_dict() for d in docs]}), 200


@folders_bp.route('/resolve-doc-ids', methods=['POST'])
@jwt_required()
def resolve_doc_ids():
    """
    Given a list of folder_ids, return all document IDs within those folders.
    Used by query and quiz endpoints.
=======

        docs = (
            db.query(Document)
            .filter_by(folder_id=folder_id, user_id=user_id)
            .order_by(Document.upload_date.desc())
            .all()
        )
        return jsonify({
            'folder': folder.to_dict(),
            'documents': [d.to_dict() for d in docs],
        }), 200


@folders_bp.route('/resolve-document-ids', methods=['POST'])
@jwt_required()
def resolve_folder_to_doc_ids():
    """
    Utility: given a list of folder_ids, return the union of all document IDs
    contained in those folders. Used by the frontend to scope queries/quizzes.
>>>>>>> Stashed changes
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    folder_ids = data.get('folder_ids', [])
<<<<<<< Updated upstream
    with get_db() as db:
        doc_ids = _resolve_folder_doc_ids(db, folder_ids, user_id)
    return jsonify({'document_ids': doc_ids}), 200
=======

    if not folder_ids:
        return jsonify({'document_ids': []}), 200

    with get_db() as db:
        docs = (
            db.query(Document.id)
            .filter(Document.user_id == user_id, Document.folder_id.in_(folder_ids))
            .all()
        )
        doc_ids = [d.id for d in docs]
        return jsonify({'document_ids': doc_ids}), 200
>>>>>>> Stashed changes
