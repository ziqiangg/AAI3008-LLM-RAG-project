"""
Language detection and translation service
Detects query language and translates for cross-lingual RAG support
"""

from langdetect import detect, DetectorFactory
from deep_translator import GoogleTranslator
import logging

logger = logging.getLogger(__name__)

# Makes langdetect deterministic (same result every run)
DetectorFactory.seed = 0 

# Supported languages map: code -> human-readable name for Gemini prompt
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'zh-cn': 'Simplified Chinese'
}

def detect_language(text: str) -> dict:
    """
    Detect the language of the input text
    
    Returns:
        dict with:
        - code: language code (e.g., 'en', 'zh-cn')
        - name: human-readable language name (e.g., 'English')
        - is_english: bool
    """
    try:
        code = detect(text)
        name = SUPPORTED_LANGUAGES.get(code, code)
        return {
            'code': code,
            'name': name,
            'is_english': code == 'en'
        }
    except Exception as e:
        logger.warning(f"Language detection failed: {e}, defaulting to English")
        return {
            'code': 'en', 'name': 'English', 'is_english': True
        }
    
def translate_to_english(text: str, source_lang: str = 'auto') -> str:
    """
    Translate text to English for embedding/retrieval.
    Returns original text if already English or translation fails
    """
    try:
        translated = GoogleTranslator(
            source=source_lang,
            target='en'
        ).translate(text)
        return translated or text
    except Exception as e:
        logger.warning(f"Translation to English failed: {e}, using original query")
        return text
