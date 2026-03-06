"""
Subject and topic classification service using embedding-based similarity
Classifies documents and chunks into predefined subject/topic hierarchy
"""
from typing import List, Dict, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
import google.generativeai as genai

from app.backend.config import Config


# Global cache for embeddings
_subject_embeddings: Optional[Dict[str, List[float]]] = None
_topic_embeddings: Optional[Dict[str, Dict[str, List[float]]]] = None
_embeddings_model: Optional[SentenceTransformer] = None


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    vec1_np = np.array(vec1)
    vec2_np = np.array(vec2)
    
    dot_product = np.dot(vec1_np, vec2_np)
    norm1 = np.linalg.norm(vec1_np)
    norm2 = np.linalg.norm(vec2_np)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return float(dot_product / (norm1 * norm2))


def initialize_classification_embeddings(embeddings_model: SentenceTransformer):
    """
    Pre-compute embeddings for all subjects and topics.
    Called once when backend starts or when first classification is needed.
    
    Args:
        embeddings_model: The sentence transformer model to use
    """
    global _subject_embeddings, _topic_embeddings, _embeddings_model
    
    if _subject_embeddings is not None:
        return  # Already initialized
    
    _embeddings_model = embeddings_model
    print("[Classification] Initializing subject and topic embeddings...")
    
    # Subject embeddings with rich, descriptive prompts
    subject_descriptions = {
        "Math": "mathematics calculus algebra geometry statistics probability equations formulas theorems proofs",
        "Computer Science": "programming algorithms data structures software coding implementation computational complexity",
        "Artificial Intelligence": "machine learning deep learning neural networks AI models training optimization computer vision natural language processing CNNs transformers",
        "Physics": "mechanics dynamics energy force momentum quantum relativity electromagnetism thermodynamics particles",
        "Chemistry": "molecules atoms reactions compounds elements bonding organic inorganic physical chemistry synthesis",
        "Biology": "cells organisms genetics DNA RNA proteins evolution ecology species life biological systems",
        "Language Learning": "grammar vocabulary pronunciation syntax morphology linguistics language acquisition translation",
        "Geography": "locations maps regions climate landforms countries continents spatial earth",
        "Economics": "markets supply demand GDP inflation prices trade financial monetary policy",
        "Social Studies": "history politics society government culture civilization historical events",
        "Computer Systems": "architecture hardware operating systems networks processors memory storage protocols",
        "General": "general information knowledge topics concepts ideas"
    }
    
    _subject_embeddings = {}
    for subject in Config.VALID_SUBJECTS:
        # Use keyword-rich descriptions for better semantic matching
        description = subject_descriptions.get(subject, subject)
        prompt = f"{subject}: {description}"
        _subject_embeddings[subject] = embeddings_model.embed_query(prompt)
    
    print(f"[Classification] Computed {len(_subject_embeddings)} subject embeddings")
    
    # Topic embeddings (hierarchical: Subject -> Topic -> Subtopic)
    _topic_embeddings = {}
    total_topics = 0
    
    for subject, tree in Config.SUBJECT_TREE.items():
        _topic_embeddings[subject] = {}
        
        for topic, subtopics in tree['topics'].items():
            for subtopic in subtopics:
                path = f"{topic}/{subtopic}"
                # Enhanced prompt with context
                prompt = f"This text discusses {subtopic} in {topic}, which is part of {subject}."
                _topic_embeddings[subject][path] = embeddings_model.embed_query(prompt)
                total_topics += 1
    
    print(f"[Classification] Computed {total_topics} topic embeddings across {len(_topic_embeddings)} subjects")
    print("[Classification] Initialization complete ✓")


def classify_document_subjects(
    content_sample: str,
    embeddings_model: SentenceTransformer,
    threshold: float = None
) -> List[Dict]:
    """
    Classify document into one or more subjects using embedding similarity.
    
    Args:
        content_sample: First ~3000 chars of document for classification
        embeddings_model: Sentence transformer model
        threshold: Minimum similarity score (defaults to Config.SUBJECT_SIMILARITY_THRESHOLD)
    
    Returns:
        List of dicts: [{"name": "Math", "confidence": 0.82}, ...]
        Sorted by confidence, descending
    """
    if threshold is None:
        threshold = Config.SUBJECT_SIMILARITY_THRESHOLD
    
    # Initialize embeddings if not done yet
    initialize_classification_embeddings(embeddings_model)
    
    # Embed the sample
    sample_embedding = embeddings_model.embed_query(content_sample)
    
    # Compare with pre-computed subject embeddings
    similarities = {}
    for subject, subj_emb in _subject_embeddings.items():
        similarities[subject] = cosine_similarity(sample_embedding, subj_emb)
    
    # Multi-subject: return all above threshold, sorted by confidence
    results = [
        {"name": subj, "confidence": float(score)}
        for subj, score in similarities.items()
        if score >= threshold
    ]
    results.sort(key=lambda x: x['confidence'], reverse=True)
    
    # Fallback to LLM classification if no embeddings match
    if not results:
        print(f"[Classification] No embedding matches above threshold {threshold}, trying LLM fallback")
        llm_subject = llm_classify_subject_fallback(content_sample)
        return [{"name": llm_subject, "confidence": 0.5}]  # Lower confidence for LLM fallback
    
    return results


def classify_chunk_topics(
    chunk_content: str,
    chunk_embedding: List[float],
    document_subjects: List[str],
    threshold: float = None
) -> List[Dict]:
    """
    Classify chunk topics within known document subjects.
    
    Args:
        chunk_content: The chunk text content
        chunk_embedding: Pre-computed embedding for the chunk
        document_subjects: List of subject names from document classification
        threshold: Minimum similarity score (defaults to Config.TOPIC_SIMILARITY_THRESHOLD)
    
    Returns:
        List of dicts with structure:
        [{
            "name": "Math",
            "confidence": 0.85,
            "topics": [
                {"name": "Calculus", "subtopic": "Derivatives", "confidence": 0.78},
                ...
            ]
        }, ...]
    """
    if threshold is None:
        threshold = Config.TOPIC_SIMILARITY_THRESHOLD
    
    if not _topic_embeddings:
        return []  # Not initialized yet
    
    results = []
    
    for subject in document_subjects:
        subject_topics = _topic_embeddings.get(subject, {})
        if not subject_topics:
            continue
        
        topic_scores = []
        
        for topic_tree_path, topic_emb in subject_topics.items():
            # topic_tree_path format: "Calculus/Derivatives"
            similarity = cosine_similarity(chunk_embedding, topic_emb)
            
            if similarity >= threshold:
                parts = topic_tree_path.split('/')
                topic_scores.append({
                    "name": parts[0],
                    "subtopic": parts[1] if len(parts) > 1 else None,
                    "confidence": float(similarity)
                })
        
        if topic_scores:
            # Sort by confidence and keep top 3
            topic_scores.sort(key=lambda x: x['confidence'], reverse=True)
            
            # Calculate average confidence for this subject's topics
            avg_confidence = sum(t['confidence'] for t in topic_scores[:3]) / min(len(topic_scores), 3)
            
            results.append({
                "name": subject,
                "confidence": float(avg_confidence),
                "topics": topic_scores[:3]  # Top 3 topics per subject
            })
    
    return results


def llm_classify_subject_fallback(content_sample: str) -> str:
    """
    Fallback: Use Gemini Flash for quick subject classification when embeddings fail.
    
    Args:
        content_sample: Text sample to classify
    
    Returns:
        Subject name (validated against VALID_SUBJECTS)
    """
    try:
        # Configure Gemini
        genai.configure(api_key=Config.GEMINI_API_KEY)
        
        prompt = f"""Classify this text into ONE category from this list:
{', '.join(Config.VALID_SUBJECTS)}

Text sample:
{content_sample[:1500]}

Return ONLY the category name, nothing else."""
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        predicted = response.text.strip()
        
        # Validate against known subjects
        if predicted in Config.VALID_SUBJECTS:
            print(f"[Classification] LLM classified as: {predicted}")
            return predicted
        
        # Try fuzzy matching
        predicted_lower = predicted.lower()
        for valid_subject in Config.VALID_SUBJECTS:
            if valid_subject.lower() in predicted_lower or predicted_lower in valid_subject.lower():
                print(f"[Classification] LLM fuzzy matched: {valid_subject}")
                return valid_subject
        
        print(f"[Classification] LLM returned invalid subject '{predicted}', defaulting to General")
        return "General"
    
    except Exception as e:
        print(f"[Classification] LLM fallback failed: {e}, defaulting to General")
        return "General"


def extract_subject_context(chunks: List[Dict]) -> Dict:
    """
    Extract subject/topic context from a list of retrieved chunks.
    Used to inform LLM generation with subject-specific guidance.
    
    Args:
        chunks: List of chunk dicts with metadata containing subject/topic info
    
    Returns:
        Dict with:
        {
            "dominant_subject": "Math",
            "subjects": ["Math", "Physics"],
            "dominant_confidence": 0.87,
            "topics": ["Calculus/Derivatives", "Mechanics/Kinematics"]
        }
    """
    if not chunks:
        return {
            "dominant_subject": "General",
            "subjects": ["General"],
            "dominant_confidence": 1.0,
            "topics": []
        }
    
    subject_counts = {}
    subject_confidences = {}
    topic_list = []
    
    for chunk in chunks:
        metadata = chunk.get('metadata', {})
        chunk_subjects = metadata.get('subjects', [])
        dominant_subject = metadata.get('dominant_subject', 'General')
        dominant_topic = metadata.get('dominant_topic', '')
        
        # Count subject occurrences
        for subj_info in chunk_subjects:
            subj_name = subj_info.get('name', 'General')
            confidence = subj_info.get('confidence', 0.5)
            
            if subj_name not in subject_counts:
                subject_counts[subj_name] = 0
                subject_confidences[subj_name] = []
            
            subject_counts[subj_name] += 1
            subject_confidences[subj_name].append(confidence)
        
        # Collect topics
        if dominant_topic and dominant_topic not in topic_list:
            topic_list.append(dominant_topic)
    
    # Determine dominant subject (most frequent + highest confidence)
    if subject_counts:
        # Sort by count first, then by average confidence
        sorted_subjects = sorted(
            subject_counts.keys(),
            key=lambda s: (subject_counts[s], np.mean(subject_confidences[s])),
            reverse=True
        )
        dominant_subject = sorted_subjects[0]
        dominant_confidence = float(np.mean(subject_confidences[dominant_subject]))
        unique_subjects = sorted_subjects[:3]  # Top 3 subjects
    else:
        dominant_subject = "General"
        dominant_confidence = 1.0
        unique_subjects = ["General"]
    
    return {
        "dominant_subject": dominant_subject,
        "subjects": unique_subjects,
        "dominant_confidence": dominant_confidence,
        "topics": topic_list[:5]  # Top 5 topics
    }


def get_dominant_subject_from_metadata(chunk_metadata: Dict) -> str:
    """
    Helper function to extract dominant subject from chunk metadata.
    
    Args:
        chunk_metadata: The chunk_metadata JSONB field
    
    Returns:
        Subject name (string)
    """
    return chunk_metadata.get('dominant_subject', 'General')
