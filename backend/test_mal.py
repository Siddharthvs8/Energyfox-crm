import os
import django
import sys
import logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai_manager.ai_meeting import _get_gemini_model, _build_system_instruction, _build_meeting_prompt

logging.basicConfig(level=logging.DEBUG)

def test_gemini():
    try:
        lang = "Malayalam"
        si = _build_system_instruction(lang)
        model = _get_gemini_model(system_instruction=si)
        print("Model initialized successfully.")
        
        prompt = "Say hello to me in Malayalam."
        print(f"Prompt: {prompt}")
        
        response = model.generate_content(prompt)
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_gemini()
