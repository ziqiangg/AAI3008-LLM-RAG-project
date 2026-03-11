"""
Folder management blueprint → /api/folders/*
Users can create folders to organise their uploaded content.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.backend.database import get_db_session as get_db
from app.backend.models import Folder, Document

folders_bp = Blueprint('folders', __name__)

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

@folders_bp.route('/', methods=['GET'])
@jwt_required()
def list_folders():
    user_id = int(get_jwt_identity())
    with get_db() as db:
        folders = (
            db.query(Folder)
              .filter_by(user_id=user_id)
              .order_by(Folder.created_at)
              .all()
        )
        return jsonify({'folders': [f.to_dict() for f in folders]}), 200


@folders_bp.route('/', methods=['POST'])
@jwt_required()
def create_folder():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Folder name is required'}), 400

    color = data.get('color', '#6c63ff')

    with get_db() as db:
        folder = Folder(user_id=user_id, name=name, color=color)
        db.add(folder)
        db.commit()
        return jsonify({'folder': folder.to_dict()}), 201


@folders_bp.route('/<int:folder_id>', methods=['PATCH'])
@jwt_required()
def update_folder(folder_id):
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404
        if 'name' in data:
            name = data['name'].strip()
            if not name:
                return jsonify({'error': 'Folder name cannot be empty'}), 400
            folder.name = name
        if 'color' in data:
            folder.color = data['color']
        db.commit()
        return jsonify({'folder': folder.to_dict()}), 200


@folders_bp.route('/<int:folder_id>', methods=['DELETE'])
@jwt_required()
def delete_folder(folder_id):
    """Delete folder but keep documents (they become unorganised)."""
    user_id = int(get_jwt_identity())
    with get_db() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404
        # Unset folder_id on all docs in this folder
        db.query(Document).filter_by(folder_id=folder_id).update({'folder_id': None})
        db.delete(folder)
        db.commit()
        return jsonify({'message': f'Folder {folder_id} deleted'}), 200


# ── Document assignment ───────────────────────────────────────────────────────

@folders_bp.route('/<int:folder_id>/documents', methods=['GET'])
@jwt_required()
def folder_documents(folder_id):
    user_id = int(get_jwt_identity())
    with get_db() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404
        docs = db.query(Document).filter_by(folder_id=folder_id, user_id=user_id).all()
        return jsonify({'documents': [d.to_dict() for d in docs]}), 200


@folders_bp.route('/resolve-doc-ids', methods=['POST'])
@jwt_required()
def resolve_doc_ids():
    """
    Given a list of folder_ids, return all document IDs within those folders.
    Used by query and quiz endpoints.
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    folder_ids = data.get('folder_ids', [])
    with get_db() as db:
        doc_ids = _resolve_folder_doc_ids(db, folder_ids, user_id)
    return jsonify({'document_ids': doc_ids}), 200
