"""
Gemini-based answer generation service
Generates contextual answers using Google's Gemini API
"""
from typing import List, Dict, Optional
import google.generativeai as genai

from app.backend.config import Config


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