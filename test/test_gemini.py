"""
Test script to verify Gemini API key functionality
"""
import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

def test_gemini_api():
    """Test if Gemini API key is working"""
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment variables")
        return False
    
    print(f"🔑 API Key found: {api_key[:20]}...")
    
    try:
        # Configure the API
        genai.configure(api_key=api_key)
        
        # List available models
        print("\n📋 Available Gemini models:")
        for model in genai.list_models():
            if 'generateContent' in model.supported_generation_methods:
                print(f"  ✓ {model.name}")
        
        # Test a simple generation
        print("\n🧪 Testing content generation...")
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Say hello in one sentence.")
        
        print(f"\n✅ Success! Response: {response.text}")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Gemini API Configuration")
    print("=" * 60)
    success = test_gemini_api()
    print("\n" + "=" * 60)
    if success:
        print("✅ Gemini API is configured correctly!")
    else:
        print("❌ Gemini API test failed. Please check your API key.")
    print("=" * 60)
