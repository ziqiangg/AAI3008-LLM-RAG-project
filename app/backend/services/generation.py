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


def build_subject_guidance(subject_context: Dict) -> str:
    """
    Generate subject-specific instructions for the LLM.
    
    Args:
        subject_context: Dict with dominant_subject, subjects, topics
    
    Returns:
        Subject-specific guidance string
    """
    dominant = subject_context.get('dominant_subject', 'General')
    topics = subject_context.get('topics', [])
    
    # Subject-specific guidance mapping
    guidance_map = {
        "Math": """\n=== MATH-SPECIFIC GUIDANCE ===
- **CRITICAL**: ALWAYS use LaTeX notation for ALL mathematical expressions, equations, and formulas
- Use $$...$$ for display math (centered on its own line) - Example: $$f(x) = \\sum_{n=0}^{\\infty} \\frac{f^{(n)}(0)}{n!}x^n$$
- Use $...$ for inline math within sentences - Example: The derivative $f'(x)$ approaches zero
- Show step-by-step solutions with clear mathematical reasoning
- Explain the intuition behind formulas and theorems
- Include worked examples with intermediate steps
- Define all variables and notation clearly
- Verify units and dimensions in calculations
- Use standard mathematical notation (∑, ∫, √, etc.) within LaTeX""",
        
        "Computer Science": """\n=== COMPUTER SCIENCE GUIDANCE ===
- Use code blocks with syntax highlighting for code examples
- Explain algorithms with time/space complexity when relevant
- Provide practical examples with edge cases
- Reference appropriate data structures and design patterns""",
        
        "Artificial Intelligence": """\n=== AI/ML GUIDANCE ===
- Explain model architectures and training processes clearly
- Include mathematical formulations when discussing algorithms
- Discuss trade-offs (accuracy vs efficiency, bias vs variance)
- Reference appropriate evaluation metrics""",
        
        "Physics": """\n=== PHYSICS GUIDANCE ===
- Always include and verify units in calculations
- Draw connections to real-world phenomena
- Use vector notation where appropriate
- Reference relevant physical laws and principles
- Explain underlying mechanisms and intuition""",
        
        "Chemistry": """\n=== CHEMISTRY GUIDANCE ===
- Include chemical formulas and equations
- Explain reaction mechanisms step-by-step
- Discuss molecular structures and bonding
- Reference relevant chemical principles and laws""",
        
        "Biology": """\n=== BIOLOGY GUIDANCE ===
- Use proper biological terminology
- Explain processes at appropriate levels (molecular, cellular, organismal)
- Draw connections between structure and function
- Reference relevant biological systems and mechanisms""",
        
        "Language Learning": """\n=== LANGUAGE LEARNING GUIDANCE ===
- Provide translations and pronunciation guidance
- Explain grammar rules with examples
- Discuss cultural context when relevant
- Include practice exercises or conversational examples""",
        
        "Physics": """\n=== GEOGRAPHY GUIDANCE ===
- Reference specific locations and their characteristics
- Discuss spatial relationships and patterns
- Include environmental and human factors
- Use directional and positional language clearly""",
        
        "Economics": """\n=== ECONOMICS GUIDANCE ===
- Explain economic concepts with real-world examples
- Discuss market dynamics and trade-offs
- Include relevant graphs and models when describing relationships
- Reference economic principles and theories""",
        
        "Social Studies": """\n=== SOCIAL STUDIES GUIDANCE ===
- Provide historical context when relevant
- Discuss multiple perspectives on events and issues
- Reference primary and secondary sources
- Connect past events to contemporary situations""",
        
        "Computer Systems": """\n=== COMPUTER SYSTEMS GUIDANCE ===
- Explain system architectures and components
- Discuss performance implications and trade-offs
- Include diagrams or descriptions of system structure
- Reference relevant protocols and standards"""
    }
    
    base_guidance = guidance_map.get(dominant, "")
    
    if topics:
        topic_str = ", ".join(topics[:3])
        base_guidance += f"\n\nRELEVANT TOPICS IN THIS CONTEXT: {topic_str}"
    
    return base_guidance


def generate_answer(
    question: str,
    context_chunks: List[Dict],
    conversation_history: Optional[List[Dict]] = None,
    subject_context: Optional[Dict] = None  # NEW parameter
) -> Dict:
    """
    Generate an answer using Gemini API based on context and conversation history.
    
    Args:
        question: User's question
        context_chunks: List of relevant document chunks (reranked)
        conversation_history: Optional list of previous messages
        subject_context: Optional dict with subject/topic information for context-aware prompts
    
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
    
    # Build subject-aware system prompt
    system_prompt = Config.SYSTEM_PROMPT
    if subject_context:
        subject_guidance = build_subject_guidance(subject_context)
        system_prompt += subject_guidance
    
    # Build the complete prompt
    prompt = f"""{system_prompt}

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
