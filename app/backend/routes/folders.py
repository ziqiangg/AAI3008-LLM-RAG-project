from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.backend.models import Folder, Document
from app.backend.database import get_db_session

folders_bp = Blueprint("folders", __name__)


@folders_bp.route("/", methods=["GET"])
@jwt_required()
def get_folders():
    """List all folders for the authenticated user."""
    user_id = int(get_jwt_identity())
    with get_db_session() as session:
        folders = session.query(Folder)\
            .filter_by(user_id=user_id)\
            .order_by(Folder.created_at)\
            .all()
        return jsonify({"folders": [f.to_dict() for f in folders]}), 200


@folders_bp.route("/", methods=["POST"])
@jwt_required()
def create_folder():
    """Create a new folder."""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    name = (data or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "Folder name is required"}), 400

    with get_db_session() as session:
        folder = Folder(user_id=user_id, name=name)
        session.add(folder)
        session.flush()
        return jsonify({"folder": folder.to_dict()}), 201


@folders_bp.route("/<int:folder_id>", methods=["PATCH"])
@jwt_required()
def rename_folder(folder_id: int):
    """Rename an existing folder."""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    name = (data or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "Folder name is required"}), 400

    with get_db_session() as session:
        folder = session.query(Folder)\
            .filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({"error": "Folder not found"}), 404
        folder.name = name
        return jsonify({"folder": folder.to_dict()}), 200


@folders_bp.route("/<int:folder_id>", methods=["DELETE"])
@jwt_required()
def delete_folder(folder_id: int):
    """Delete a folder. Documents inside are moved out (folder_id set to NULL)."""
    user_id = int(get_jwt_identity())
    with get_db_session() as session:
        folder = session.query(Folder)\
            .filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            return jsonify({"error": "Folder not found"}), 404
        # Documents are automatically unlinked via ON DELETE SET NULL
        session.delete(folder)
        return jsonify({"message": f"Folder '{folder.name}' deleted."}), 200
