import os
import django
import sys
import logging
import google.generativeai as genai
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

genai.configure(api_key=settings.GEMINI_API_KEY)

def test_gemini():
    try:
        model = genai.GenerativeModel('gemini-1.5-flash', system_instruction="Response in Malayalam")
        response = model.generate_content("Say hello")
        print(f"1.5 flash Response: {response.text}")
    except Exception as e:
        print(f"1.5 Error: {e}")

    try:
        model2 = genai.GenerativeModel('gemini-2.0-flash', system_instruction="Response in Malayalam")
        response2 = model2.generate_content("Say hello")
        print(f"2.0 flash Response: {response2.text}")
    except Exception as e:
        print(f"2.0 Error: {e}")

if __name__ == "__main__":
    test_gemini()
