"""
Folder management blueprint → /api/folders/*
Allows users to create, list, rename, and delete folders for organizing documents.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.backend.database import get_db_session as get_db
from app.backend.models import Folder, Document

folders_bp = Blueprint('folders', __name__)


@folders_bp.route('/', methods=['GET'])
@jwt_required()
def list_folders():
    """List all folders for the authenticated user, including document counts."""
    user_id = int(get_jwt_identity())
    with get_db() as db:
        folders = (
            db.query(Folder)
            .filter_by(user_id=user_id)
            .order_by(Folder.name)
            .all()
        )
        return jsonify({'folders': [f.to_dict() for f in folders]}), 200


@folders_bp.route('/', methods=['POST'])
@jwt_required()
def create_folder():
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
        db.add(folder)
        db.commit()
        return jsonify({'folder': folder.to_dict()}), 201


@folders_bp.route('/<int:folder_id>', methods=['PATCH'])
@jwt_required()
def rename_folder(folder_id):
    """Rename an existing folder."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()

    if not name:
        return jsonify({'error': 'New folder name is required'}), 400

    with get_db() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404

        # Check for duplicate names
        dup = db.query(Folder).filter_by(user_id=user_id, name=name).first()
        if dup and dup.id != folder_id:
            return jsonify({'error': f'A folder named "{name}" already exists'}), 409

        folder.name = name
        db.commit()
        return jsonify({'folder': folder.to_dict()}), 200


@folders_bp.route('/<int:folder_id>', methods=['DELETE'])
@jwt_required()
def delete_folder(folder_id):
    """
    Delete a folder. Documents inside are moved to 'unfiled' (folder_id = NULL),
    NOT deleted.
    """
    user_id = int(get_jwt_identity())
    with get_db() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404

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
    user_id = int(get_jwt_identity())
    with get_db() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404

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
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    folder_ids = data.get('folder_ids', [])

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
