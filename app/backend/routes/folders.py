"""
Folder management blueprint → /api/folders/*
Provides CRUD operations for organizing documents into folders
"""
import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from app.backend.database import get_db_session
from app.backend.models import Folder, Document

folders_bp = Blueprint('folders', __name__)
logger = logging.getLogger(__name__)


@folders_bp.route('/', methods=['GET'])
@jwt_required()
def list_folders():
    """
    List user's folders with document counts.
    
    Returns:
        JSON: {folders: [{id, name, document_count, created_at}, ...]}
    """
    user_id = int(get_jwt_identity())
    
    with get_db_session() as db:
        # Join with documents to get counts
        folders = (
            db.query(
                Folder.id,
                Folder.name,
                Folder.created_at,
                func.count(Document.id).label('document_count')
            )
            .outerjoin(Document, Folder.id == Document.folder_id)
            .filter(Folder.user_id == user_id)
            .group_by(Folder.id, Folder.name, Folder.created_at)
            .order_by(Folder.created_at.desc())
            .all()
        )
        
        result = [{
            'id': f.id,
            'name': f.name,
            'document_count': f.document_count,
            'created_at': f.created_at.isoformat()
        } for f in folders]
        
        return jsonify({'folders': result}), 200


@folders_bp.route('/', methods=['POST'])
@jwt_required()
def create_folder():
    """
    Create new folder.
    
    Expected JSON: {name: str}
    
    Returns:
        JSON: {id, name, document_count, created_at}
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    
    if not name:
        return jsonify({'error': 'Folder name is required'}), 400
    
    if len(name) > 255:
        return jsonify({'error': 'Folder name too long (max 255 chars)'}), 400
    
    with get_db_session() as db:
        # Check for duplicate
        existing = db.query(Folder).filter_by(user_id=user_id, name=name).first()
        if existing:
            return jsonify({'error': f'Folder "{name}" already exists'}), 409
        
        folder = Folder(user_id=user_id, name=name)
        db.add(folder)
        db.flush()
        
        result = {
            'id': folder.id,
            'name': folder.name,
            'document_count': 0,
            'created_at': folder.created_at.isoformat()
        }
        
        db.commit()
        logger.info(f"[Folders] Created folder '{name}' (id={folder.id}) for user {user_id}")
        return jsonify(result), 201


@folders_bp.route('/<int:folder_id>', methods=['PATCH'])
@jwt_required()
def rename_folder(folder_id):
    """
    Rename folder.
    
    Expected JSON: {name: str}
    
    Returns:
        JSON: {id, name}
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    new_name = (data.get('name') or '').strip()
    
    if not new_name:
        return jsonify({'error': 'New name is required'}), 400
    
    if len(new_name) > 255:
        return jsonify({'error': 'Folder name too long (max 255 chars)'}), 400
    
    with get_db_session() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404
        
        # Check for name conflict
        existing = db.query(Folder).filter(
            Folder.user_id == user_id,
            Folder.name == new_name,
            Folder.id != folder_id
        ).first()
        if existing:
            return jsonify({'error': f'Folder "{new_name}" already exists'}), 409
        
        old_name = folder.name
        folder.name = new_name
        db.commit()
        
        logger.info(f"[Folders] Renamed folder {folder_id} from '{old_name}' to '{new_name}' for user {user_id}")
        return jsonify({'id': folder.id, 'name': folder.name}), 200


@folders_bp.route('/<int:folder_id>', methods=['DELETE'])
@jwt_required()
def delete_folder(folder_id):
    """
    Delete folder. Documents in folder become unfiled (folder_id=NULL).
    
    Returns:
        JSON: {message: str}
    """
    user_id = int(get_jwt_identity())
    
    with get_db_session() as db:
        folder = db.query(Folder).filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404
        
        folder_name = folder.name
        
        # Count documents in folder before deletion
        doc_count = db.query(func.count(Document.id)).filter_by(folder_id=folder_id).scalar()
        
        # ON DELETE SET NULL in schema handles documents automatically
        db.delete(folder)
        db.commit()
        
        logger.info(f"[Folders] Deleted folder '{folder_name}' (id={folder_id}, {doc_count} docs unfiled) for user {user_id}")
        return jsonify({'message': f'Folder deleted. {doc_count} document(s) moved to unfiled.'}), 200
