"""
Gemini-based answer generation service
Generates contextual answers using Google's Gemini API
"""
import re
import json
import logging
from typing import List, Dict, Optional
import google.generativeai as genai

from app.backend.config import Config
# Import formatting functions from modular prompt_builder
from app.backend.services.prompt_builder import (
    format_context_section as format_context,
    format_history_section as format_conversation_history,
)

logger = logging.getLogger(__name__)
# Configure Gemini API once
_configured = False


def configure_gemini():
    """Configure Gemini API with API key from config"""
    global _configured
    if not _configured:
        genai.configure(api_key=Config.GEMINI_API_KEY)
        _configured = True


def generate_answer(
    question: str,
    context_chunks: List[Dict],
    conversation_history: Optional[List[Dict]] = None,
    subject_context: Optional[Dict] = None,
    language_info: Optional[Dict] = None,
    web_enabled: bool = False
) -> Dict:
    """
    Generate an answer using Gemini API based on context and conversation history.
    Prompt assembly delegated to prompt_builder module.

    Args:
        question: User's question
        context_chunks: List of relevant document chunks (reranked, docs + web)
        conversation_history: Optional list of previous messages
        subject_context: Optional dict with subject/topic information
        language_info: Optional dict with language info {'code', 'name', 'is_english'}
        web_enabled: Whether web search is active (toggle or explicit)

    Returns:
        Dict containing:
            - answer: Generated answer text
            - model_used: Model identifier
            - finish_reason: Completion status
    """
    configure_gemini()

    # Import here to avoid circular dependency
    from app.backend.services.prompt_builder import build_prompt
    
    # Dynamic prompt assembly
    prompt = build_prompt(
        question=question,
        context_chunks=context_chunks,
        conversation_history=conversation_history,
        subject_context=subject_context,
        language_info=language_info,
        web_enabled=web_enabled
    )

    # Initialize model
    model = genai.GenerativeModel(
        model_name=Config.LLM_MODEL,
        generation_config={
            'temperature': Config.LLM_TEMPERATURE,
            'max_output_tokens': Config.MAX_TOKENS,
        }
    )

    # Generate response
    try:
        response = model.generate_content(prompt)

        return {
            'answer': response.text,
            'model_used': Config.LLM_MODEL,
            'finish_reason': getattr(response, 'finish_reason', 'COMPLETED')
        }

    except Exception as e:
        # Handle API errors gracefully
        error_msg = f"Error generating response: {str(e)}"
        return {
            'answer': (
                "I apologize, but I encountered an error while generating the response. "
                "Please try rephrasing your question or contact support if the issue persists.\n\n"
                f"Error details: {error_msg}"
            ),
            'model_used': Config.LLM_MODEL,
            'finish_reason': 'ERROR'
        }
    
def build_quiz_prompt(
    num_questions: int,
    difficulty: str,
    question_type: str,
    topic: Optional[str],
    context_chunks: List[Dict],
) -> str:
    """
    Build the quiz generation prompt from config and retrieved chunks.

    Args:
        num_questions:  Number of questions to generate (1-20)
        difficulty:     "easy" | "medium" | "hard"
        question_type:  "mcq" | "multi_select" | "mixed"
        topic:          Optional focus topic from the user
        context_chunks: Retrieved and reranked document chunks

    Returns:
        Complete prompt string ready to send to Gemini
    """
    formatted_context = format_context(context_chunks)   # reuse existing helper

    difficulty_guide = {
        'easy':   'Direct recall of explicit facts stated in the context.',
        'medium': 'Require understanding and inference from the context.',
        'hard':   'Require analysis, application, or synthesis across multiple pieces of context. Use challenging distractors.',
    }[difficulty]

    type_guide = {
        'mcq':          'All questions must be single-answer MCQ (exactly 1 correct option).',
        'multi_select': 'All questions must be multi-select (2–3 correct options). Each question stem must begin with "Select all that apply:".',
        'mixed':        f'Mix single-answer MCQ and multi-select across the {num_questions} questions. Multi-select question stems must begin with "Select all that apply:".',
    }[question_type]

    topic_instruction = (
        f'\nFOCUS TOPIC: Prioritise questions related to "{topic}".\n'
        if topic else ''
    )

    return f"""You are an expert quiz generator for a student learning platform.
Generate exactly {num_questions} questions based ONLY on the context provided below. Do not use external knowledge.

DIFFICULTY: {difficulty.upper()} — {difficulty_guide}
FORMAT: {type_guide}{topic_instruction}

RULES:
- Exactly 4 options per question, labelled A, B, C, D.
- MCQ: exactly 1 correct answer in the "correct" list.
- Multi-select: 2 or 3 correct answers in the "correct" list.
- Distractors must be plausible — not trivially wrong.
- Explanation must quote or closely paraphrase the source text that supports the correct answer.
- Vary question styles: definitions, cause-and-effect, comparisons, application.
- Do NOT invent facts not present in the context.

Return ONLY valid JSON — no markdown fences, no extra commentary:
{{
  "questions": [
    {{
      "id": 1,
      "type": "mcq",
      "question": "...",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "correct": ["A"],
      "explanation": "..."
    }}
  ]
}}

=== CONTEXT ===
{formatted_context}
"""

def generate_quiz(
    num_questions: int,
    difficulty: str,
    question_type: str,
    context_chunks: List[Dict],
    topic: Optional[str] = None,
) -> Dict:
    """
    Generate a quiz grounded in retrieved document chunks via Gemini.

    Args:
        num_questions:  Number of questions to generate (1-20)
        difficulty:     "easy" | "medium" | "hard"
        question_type:  "mcq" | "multi_select" | "mixed"
        context_chunks: Retrieved and reranked document chunks
        topic:          Optional focus topic from the user

    Returns:
        Dict with:
        - questions: List of parsed question dicts
        - model_used: Model identifier
        OR raises ValueError on parse failure
    """
    configure_gemini()   # reuse existing helper — no-op if already configured

    prompt = build_quiz_prompt(
        num_questions  = num_questions,
        difficulty     = difficulty,
        question_type  = question_type,
        topic          = topic,
        context_chunks = context_chunks,
    )

    model = genai.GenerativeModel(
        model_name        = Config.LLM_MODEL,
        generation_config = {
            'temperature':      0.4,
            'max_output_tokens': 8192,
        }
    )

    try:
        response = model.generate_content(prompt)
        raw      = response.text.strip()
    except Exception as e:
        logger.error(f'[Quiz] Gemini API error: {e}')
        raise RuntimeError(f'Gemini API call failed: {e}') from e

    # Strip markdown fences if the model wraps output despite instructions
    clean = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    clean = re.sub(r'\s*```$',          '', clean, flags=re.MULTILINE).strip()

    try:
        quiz_data = json.loads(clean)
    except json.JSONDecodeError as e:
        logger.error(f'[Quiz] JSON parse error: {e}\nRaw output: {raw[:600]}')
        raise ValueError(f'Model returned malformed JSON: {e}') from e

    questions = quiz_data.get('questions', [])
    if not questions:
        raise ValueError('Model returned no questions.')

    return {
        'questions':  questions,
        'model_used': Config.LLM_MODEL,
    }
