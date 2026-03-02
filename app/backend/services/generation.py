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


def format_context(chunks: List[Dict]) -> str:
    """
    Format retrieved chunks into numbered context sections.
    
    Args:
        chunks: List of chunk dicts with content and metadata
    
    Returns:
        Formatted context string
    """
    if not chunks:
        return "No relevant context found in the uploaded documents."
    
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        filename = chunk.get('filename', 'Unknown')
        content = chunk.get('content', '')
        chunk_order = chunk.get('chunk_order', '?')
        
        context_parts.append(
            f"[Source {i}] {filename} (Section {chunk_order}):\n{content}"
        )
    
    return "\n\n".join(context_parts)


def format_conversation_history(messages: List[Dict]) -> str:
    """
    Format conversation history into a readable string.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
    
    Returns:
        Formatted conversation history
    """
    if not messages:
        return "No previous conversation."
    
    history_parts = []
    for msg in messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        if role == 'user':
            history_parts.append(f"Student: {content}")
        elif role == 'assistant':
            history_parts.append(f"Assistant: {content}")
    
    return "\n".join(history_parts)


def generate_answer(
    question: str,
    context_chunks: List[Dict],
    conversation_history: Optional[List[Dict]] = None
) -> Dict:
    """
    Generate an answer using Gemini API based on context and conversation history.
    
    Args:
        question: User's question
        context_chunks: List of relevant document chunks (reranked)
        conversation_history: Optional list of previous messages
    
    Returns:
        Dict containing:
            - answer: Generated answer text
            - model_used: Model identifier
            - finish_reason: Completion status
    """
    configure_gemini()
    
    # Format context and history
    formatted_context = format_context(context_chunks)
    formatted_history = ""
    
    if conversation_history and len(conversation_history) > 0:
        formatted_history = "\n\n=== PREVIOUS CONVERSATION ===\n" + \
                          format_conversation_history(conversation_history) + "\n"
    
    # Build the complete prompt
    prompt = f"""{Config.SYSTEM_PROMPT}

=== RETRIEVED CONTEXT FROM DOCUMENTS ===
{formatted_context}
{formatted_history}
=== CURRENT QUESTION ===
{question}

Please provide a comprehensive answer based on the context above. Include citations to specific sources when referencing information."""
    
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
            'answer': f"I apologize, but I encountered an error while generating the response. Please try rephrasing your question or contact support if the issue persists.\n\nError details: {error_msg}",
            'model_used': Config.LLM_MODEL,
            'finish_reason': 'ERROR'
        }
