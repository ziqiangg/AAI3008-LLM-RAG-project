"""
Query Rewriting Service for RAG Pipeline
==========================================

Implements intelligent query rewriting strategies to improve retrieval quality:
- Conversational context fusion: Resolves pronouns and incorporates conversation history
- Query expansion: Generates synonymous variants for better recall
- Query decomposition: Breaks complex multi-intent questions into sub-queries
- HyDE: Generates hypothetical documents for semantic gap bridging

Author: AAI3008 Team
Date: March 2026
"""

import re
import logging
from typing import List, Dict, Optional, Union
import google.generativeai as genai

from app.backend.config import Config

logger = logging.getLogger(__name__)


class QueryRewriter:
    """
    Intelligent query rewriting for improved RAG retrieval.
    
    Strategies:
    1. Conversational Context Fusion - Resolve pronouns using conversation history
    2. Query Expansion - Generate synonymous variants
    3. Query Decomposition - Split complex questions
    4. HyDE - Generate hypothetical documents for better semantic matching
    """
    
    def __init__(self, llm_model: Optional[str] = None):
        """
        Initialize query rewriter with LLM model.
        
        Args:
            llm_model: Optional LLM model name (defaults to Config.LLM_MODEL)
        """
        self.llm_model = llm_model or Config.LLM_MODEL
        self._configure_gemini()
    
    def _configure_gemini(self):
        """Configure Gemini API with credentials."""
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
        except Exception as e:
            logger.warning(f"[QueryRewriter] Failed to configure Gemini: {e}")
    
    # ════════════════════════════════════════════════════════════════
    # STRATEGY 1: CONVERSATIONAL CONTEXT FUSION
    # ════════════════════════════════════════════════════════════════
    
    def rewrite_with_conversation_context(
        self,
        current_query: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> str:
        """
        Rewrite query by incorporating conversation context to resolve references.
        
        Use cases:
        - Pronouns: "How does it work?" → "How does gradient descent work?"
        - Implicit references: "Explain more" → "Explain gradient descent in detail"
        - Follow-up questions: "What about backprop?" → "What about backpropagation in gradient descent?"
        
        Args:
            current_query: User's current question
            conversation_history: List of previous messages [{'role': 'user'|'assistant', 'content': str}]
        
        Returns:
            Rewritten self-contained query
        """
        if not conversation_history or len(conversation_history) < 2:
            logger.debug(f"[QueryRewriter] No conversation context, returning original query")
            return current_query
        
        # Check if query needs rewriting (has pronouns or is very short)
        if not self._needs_context_fusion(current_query):
            logger.debug(f"[QueryRewriter] Query doesn't need context fusion: {current_query}")
            return current_query
        
        try:
            # Format conversation history (last 4 messages for context window)
            history_text = self._format_history_for_rewrite(conversation_history[-4:])
            
            prompt = f"""You are a query rewriter for a search system.

Given this conversation history:
{history_text}

The user asks: "{current_query}"

Rewrite this question to be self-contained by:
1. Resolving pronouns (it, they, this, that, these, those) to specific concepts from history
2. Incorporating implicit context from previous messages
3. Keeping the user's original language and intent EXACTLY
4. Making it explicit and clear for semantic search
5. If the query is already clear and self-contained, return it unchanged

IMPORTANT: 
- Preserve the original language (English/Chinese/etc.)
- Keep the same meaning and user intent
- Only add necessary context, don't change the question structure
- If no context is needed, return the original question

Rewritten question (one line only):"""
            
            model = genai.GenerativeModel(self.llm_model)
            response = model.generate_content(
                prompt,
                generation_config={
                    'temperature': 0.3,  # Low temperature for consistent rewriting
                    'max_output_tokens': 200,
                }
            )
            
            rewritten = response.text.strip()
            
            # Clean up response (remove quotes, extra whitespace)
            rewritten = self._clean_rewritten_query(rewritten)
            
            # Validation: ensure rewritten is reasonable
            if not rewritten or len(rewritten) < 3 or len(rewritten) > 500:
                logger.warning(f"[QueryRewriter] Invalid rewritten query, using original")
                return current_query
            
            logger.info(f"[QueryRewriter] Context fusion applied")
            logger.info(f"  Original: {current_query}")
            logger.info(f"  Rewritten: {rewritten}")
            
            return rewritten
        
        except Exception as e:
            logger.error(f"[QueryRewriter] Context fusion failed: {e}")
            return current_query  # Fallback to original
    
    def _needs_context_fusion(self, query: str) -> bool:
        """
        Determine if query needs conversation context fusion.
        
        Indicators:
        - Contains pronouns (it, that, this, they, etc.)
        - Very short (< 15 chars)
        - Starts with "how about", "what about", "explain more", etc.
        """
        query_lower = query.lower().strip()
        
        # Check for pronouns
        pronouns = ['it', 'this', 'that', 'these', 'those', 'they', 'them', 'its', 'their']
        has_pronoun = any(
            re.search(r'\b' + pronoun + r'\b', query_lower) 
            for pronoun in pronouns
        )
        
        # Check for follow-up phrases
        followup_phrases = [
            'how about', 'what about', 'tell me more', 'explain more',
            'can you explain', 'go on', 'continue', 'and', 'also'
        ]
        starts_with_followup = any(
            query_lower.startswith(phrase) 
            for phrase in followup_phrases
        )
        
        # Check if very short (likely incomplete)
        is_very_short = len(query.strip()) < 15
        
        return has_pronoun or starts_with_followup or is_very_short
    
    def _format_history_for_rewrite(self, history: List[Dict]) -> str:
        """Format conversation history for LLM prompt."""
        formatted = []
        for msg in history:
            role = "Student" if msg['role'] == 'user' else "Assistant"
            content = msg['content'][:300]  # Truncate long messages
            formatted.append(f"{role}: {content}")
        return "\n".join(formatted)
    
    def _clean_rewritten_query(self, text: str) -> str:
        """Clean up LLM-generated rewritten query."""
        if not text:
            return ''

        # Strip markdown code fences if model returns wrapped text.
        text = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', text.strip())
        text = re.sub(r'\s*```$', '', text)

        # Remove quotes
        text = text.strip('"\'')
        
        # Remove common prefixes the LLM might add
        prefixes_to_remove = [
            "rewritten question:",
            "rewritten:",
            "answer:",
            "query:",
        ]
        text_lower = text.lower()
        for prefix in prefixes_to_remove:
            if text_lower.startswith(prefix):
                text = text[len(prefix):].strip()
                text = text.strip(':').strip()
        
        # Normalize repeated whitespace while preserving line breaks.
        lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines).strip()
    
    # ════════════════════════════════════════════════════════════════
    # STRATEGY 2: QUERY EXPANSION (Multi-Variant)
    # ════════════════════════════════════════════════════════════════
    
    def expand_query_with_synonyms(
        self,
        original_query: str,
        num_variants: int = 2
    ) -> List[str]:
        """
        Generate alternative phrasings with different terminology.
        
        Use cases:
        - Vocabulary mismatch: "compute gradients" vs "calculate derivatives"
        - Technical jargon: Multiple ways to describe same concept
        
        Args:
            original_query: User's question
            num_variants: Number of alternative phrasings (default: 2)
        
        Returns:
            List of query variants including original
        """
        try:
            prompt = f"""Generate {num_variants} alternative phrasings of this question using different but equivalent terminology:

Original: "{original_query}"

Requirements:
- Keep the same meaning and intent
- Use synonyms and related technical terms  
- Maintain the original language
- Each variant should be distinct but semantically equivalent
- Do not add new information or change the question type

Output format (one variant per line):
1. [variant 1]
2. [variant 2]"""
            
            model = genai.GenerativeModel(self.llm_model)
            response = model.generate_content(
                prompt,
                generation_config={
                    'temperature': 0.7,  # Moderate temperature for diversity
                    'max_output_tokens': 300,
                }
            )
            
            # Parse numbered list
            variants = self._parse_numbered_variants(response.text)
            
            # Always include original first
            all_variants = [original_query] + variants
            
            logger.info(f"[QueryRewriter] Expanded query into {len(all_variants)} variants")
            for i, v in enumerate(all_variants):
                logger.debug(f"  Variant {i}: {v}")
            
            return all_variants[:num_variants + 1]  # Original + N variants
        
        except Exception as e:
            logger.error(f"[QueryRewriter] Query expansion failed: {e}")
            return [original_query]  # Fallback to original only
    
    def _parse_numbered_variants(self, text: str) -> List[str]:
        """Parse numbered/bulleted variants from LLM response with resilient fallbacks."""
        if not text:
            return []

        variants = []

        # Match one-item-per-line lists:
        # 1. item / 1) item / - item / * item / • item
        for line in text.strip().split('\n'):
            line = line.strip()
            match = re.match(r'^(?:\d+[\.)]|[-\*•])\s*(.+)$', line)
            if match:
                variant = self._clean_rewritten_query(match.group(1).strip('"\''))
                if variant and len(variant) > 5:
                    variants.append(variant)

        # Fallback: inline numbered list in a single line, e.g. "1. A 2. B 3. C"
        if not variants:
            inline_parts = [
                self._clean_rewritten_query(p)
                for p in re.split(r'\s*\d+[\.)]\s*', text)
                if p and p.strip()
            ]
            variants = [p for p in inline_parts if len(p) > 5]

        # Deduplicate while preserving order.
        deduped = []
        seen = set()
        for v in variants:
            k = v.lower()
            if k in seen:
                continue
            seen.add(k)
            deduped.append(v)

        return deduped

    def _heuristic_decompose_query(self, query: str) -> List[str]:
        """Fallback decomposition when LLM output is under-segmented."""
        q = query.strip().rstrip('?')
        if not q:
            return [query]

        parts = re.split(r'\s+(?:and|&|vs\.?|versus)\s+', q, flags=re.IGNORECASE)
        parts = [p.strip(' ,;') for p in parts if p.strip(' ,;')]

        if len(parts) <= 1:
            return [query]

        lead = "Explain"
        lower_q = q.lower()
        if lower_q.startswith('what is'):
            lead = "What is"
        elif lower_q.startswith('what are'):
            lead = "What are"
        elif lower_q.startswith('describe'):
            lead = "Describe"

        sub_questions = []
        for part in parts:
            p = part.strip()
            if not p:
                continue
            # Avoid doubling helper verbs if already phrased as a question fragment.
            if re.match(r'^(what|how|why|when|where|which)\b', p, flags=re.IGNORECASE):
                sq = p
            else:
                sq = f"{lead} {p}"
            if not sq.endswith('?'):
                sq += '?'
            sub_questions.append(sq)

        return sub_questions if len(sub_questions) > 1 else [query]
    
    # ════════════════════════════════════════════════════════════════
    # STRATEGY 3: QUERY DECOMPOSITION
    # ════════════════════════════════════════════════════════════════
    
    def decompose_complex_query(self, query: str) -> List[str]:
        """
        Break down complex multi-intent questions into focused sub-questions.
        
        Use cases:
        - "What is X and how does it differ from Y?" → ["What is X?", "What is Y?", "How does X differ from Y?"]
        - "Explain A, B, and C" → ["Explain A", "Explain B", "Explain C"]
        
        Args:
            query: User's complex question
        
        Returns:
            List of sub-questions (returns [original] if already focused)
        """
        try:
            prompt = f"""Analyze this question and determine if it contains multiple distinct intents or topics.

Question: "{query}"

If it has multiple intents, break it down into 2-4 focused sub-questions that together answer the original.
If it's already focused on one topic, return just the original question.

Examples:
- "What is supervised learning and how is it different from unsupervised?" → 
  1. What is supervised learning?
  2. What is unsupervised learning?
  3. How does supervised learning differ from unsupervised learning?

- "Explain gradient descent" → 
  1. Explain gradient descent

Output format (numbered list, one per line):"""
            
            model = genai.GenerativeModel(self.llm_model)
            response = model.generate_content(
                prompt,
                generation_config={
                    'temperature': 0.5,
                    'max_output_tokens': 400,
                }
            )
            
            sub_questions = self._parse_numbered_variants(response.text)

            # Fallback for under-segmented outputs on clearly compound questions.
            if len(sub_questions) <= 1 and self._is_compound_question(query):
                fallback_parts = self._heuristic_decompose_query(query)
                if len(fallback_parts) > len(sub_questions):
                    logger.info(
                        f"[QueryRewriter] Using heuristic decomposition fallback: {len(fallback_parts)} parts"
                    )
                    sub_questions = fallback_parts
            
            # If no sub-questions generated, return original
            if len(sub_questions) == 0:
                logger.debug(f"[QueryRewriter] No sub-questions generated")
                return [query]
            
            # If only 1 sub-question and it's identical to original, return original
            if len(sub_questions) == 1 and sub_questions[0].strip().lower() == query.strip().lower():
                logger.debug(f"[QueryRewriter] Query is already focused, no decomposition needed")
                return [query]
            
            # Either 2+ sub-questions, or 1 improved/clarified sub-question
            logger.info(f"[QueryRewriter] Decomposed into {len(sub_questions)} sub-question(s)")
            for i, sq in enumerate(sub_questions, 1):
                logger.debug(f"  Sub-Q{i}: {sq}")
            
            return sub_questions
        
        except Exception as e:
            logger.error(f"[QueryRewriter] Query decomposition failed: {e}")
            return [query]  # Fallback to original
    
    # ════════════════════════════════════════════════════════════════
    # STRATEGY 4: HyDE (Hypothetical Document Embedding)
    # ════════════════════════════════════════════════════════════════
    
    def generate_hypothetical_document(self, query: str) -> str:
        """
        Generate a hypothetical document that would answer the query.
        
        Use case: Bridge semantic gap between question style and document style.
        The hypothetical document embedding is used instead of query embedding.
        
        Args:
            query: User's question
        
        Returns:
            Hypothetical document text (2-3 sentences)
        """
        try:
            prompt = f"""You are generating a hypothetical passage that would answer this question.
Write a detailed, factual passage (2-3 sentences, ~50-100 words) that directly answers:

"{query}"

Write as if this passage exists in a textbook or documentation.
Do not mention uncertainty or that you're generating a hypothetical.
Just write the factual passage.

Passage:"""
            
            model = genai.GenerativeModel(self.llm_model)
            response = model.generate_content(
                prompt,
                generation_config={
                    'temperature': 0.5,
                    'max_output_tokens': 200,
                }
            )
            
            hypothetical_doc = self._clean_rewritten_query(response.text or "")

            # Ensure HyDE output is substantive enough for retrieval + UI display.
            # Retry once with stricter constraints if too short.
            if len(hypothetical_doc.split()) < 18:
                retry_prompt = f"""Write a factual passage that directly answers this query.
Requirements:
- 2 to 3 complete sentences
- 60 to 100 words
- Include concrete terminology from the query
- No bullet points, no headings

Query: \"{query}\"

Passage:"""
                retry = model.generate_content(
                    retry_prompt,
                    generation_config={
                        'temperature': 0.4,
                        'max_output_tokens': 260,
                    }
                )
                retry_text = self._clean_rewritten_query(retry.text or "")
                if len(retry_text.split()) >= len(hypothetical_doc.split()):
                    hypothetical_doc = retry_text
            
            logger.info(f"[QueryRewriter] HyDE generated hypothetical document")
            logger.debug(f"  Query: {query}")
            logger.debug(f"  HyDE Doc: {hypothetical_doc[:150]}...")
            
            return hypothetical_doc if hypothetical_doc else query
        
        except Exception as e:
            logger.error(f"[QueryRewriter] HyDE generation failed: {e}")
            return query  # Fallback to original query
    
    # ════════════════════════════════════════════════════════════════
    # UTILITY: Strategy Selection
    # ════════════════════════════════════════════════════════════════
    
    def analyze_query_needs(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None,
        avg_rerank_score: Optional[float] = None
    ) -> str:
        """
        Intelligently determine which rewriting strategy to use.
        
        Args:
            query: User's question
            conversation_history: Previous conversation messages
            avg_rerank_score: Average rerank score from retrieval (if available)
        
        Returns:
            Strategy name: 'conversation_context', 'expansion', 'decomposition', 'hyde', or 'none'
        """
        # Priority 1: Conversational context fusion (has pronouns + history)
        if conversation_history and len(conversation_history) >= 2:
            if self._needs_context_fusion(query):
                return 'conversation_context'
        
        # Priority 2: Query decomposition (compound questions)
        if self._is_compound_question(query):
            return 'decomposition'
        
        # Priority 3: HyDE (very low scores, likely semantic gap)
        if avg_rerank_score is not None and avg_rerank_score < 0.2:
            return 'hyde'
        
        # Priority 4: Query expansion (moderate scores, may help recall)
        if avg_rerank_score is not None and 0.2 <= avg_rerank_score < 2.0:
            return 'expansion'
        
        # No rewriting needed
        return 'none'
    
    def _is_compound_question(self, query: str) -> bool:
        """Check if query contains multiple intents."""
        # Look for conjunction patterns
        compound_indicators = [
            ' and ', ' or ', ' but ', ' also ',
            ' as well as ', ' in addition to ',
            'explain both', 'compare', 'difference between',
            'what are', 'list', 'enumerate'
        ]
        
        query_lower = query.lower()
        
        # Check for conjunctions
        has_conjunction = any(indicator in query_lower for indicator in compound_indicators)
        
        # Check for multiple question marks or commas
        has_multiple_parts = query.count('?') > 1 or query.count(',') >= 2
        
        return has_conjunction or has_multiple_parts


# ════════════════════════════════════════════════════════════════
# SINGLETON PATTERN
# ════════════════════════════════════════════════════════════════

_rewriter_instance = None

def get_query_rewriter() -> QueryRewriter:
    """Get or create singleton QueryRewriter instance."""
    global _rewriter_instance
    if _rewriter_instance is None:
        _rewriter_instance = QueryRewriter()
        logger.info("[QueryRewriter] Initialized query rewriter service")
    return _rewriter_instance
