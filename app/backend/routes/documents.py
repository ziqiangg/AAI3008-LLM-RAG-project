"""
Document management routes
"""
from flask import Blueprint, request, jsonify
from app.backend.database import get_db_session
from app.backend.models import Document, User
from datetime import datetime

documents_bp = Blueprint('documents', __name__)


@documents_bp.route('/', methods=['GET'])
def get_documents():
    """Get all documents (optionally filtered by user_id)"""
    session = get_db_session()
    try:
        user_id = request.args.get('user_id', type=int)
        
        if user_id:
            documents = session.query(Document).filter_by(user_id=user_id).all()
        else:
            documents = session.query(Document).all()
        
        return jsonify([doc.to_dict() for doc in documents]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@documents_bp.route('/<int:document_id>', methods=['GET'])
def get_document(document_id):
    """Get document by ID"""
    session = get_db_session()
    try:
        document = session.query(Document).filter_by(id=document_id).first()
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        return jsonify(document.to_dict()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@documents_bp.route('/', methods=['POST'])
def create_document():
    """Create a new document record"""
    session = get_db_session()
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['user_id', 'filename', 'file_path']
        if not all(field in data for field in required_fields):
            return jsonify({'error': f'Required fields: {", ".join(required_fields)}'}), 400
        
        # Check if user exists
        user = session.query(User).filter_by(id=data['user_id']).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        document = Document(
            user_id=data['user_id'],
            filename=data['filename'],
            file_path=data['file_path'],
            file_type=data.get('file_type'),
            title=data.get('title'),
            subject=data.get('subject')
        )
        
        session.add(document)
        session.commit()
        
        return jsonify(document.to_dict()), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@documents_bp.route('/<int:document_id>', methods=['DELETE'])
def delete_document(document_id):
    """Delete a document"""
    session = get_db_session()
    try:
        document = session.query(Document).filter_by(id=document_id).first()
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        session.delete(document)
        session.commit()
        
        return jsonify({'message': 'Document deleted successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@documents_bp.route('/<int:document_id>/chunks', methods=['GET'])
def get_document_chunks(document_id):
    """Get all chunks for a document"""
    session = get_db_session()
    try:
        document = session.query(Document).filter_by(id=document_id).first()
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        chunks = [chunk.to_dict() for chunk in document.chunks]
        return jsonify(chunks), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()
