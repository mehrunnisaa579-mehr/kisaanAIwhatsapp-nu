import os
import sys
import logging
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_dotenv_model(working_model: str):
    try:
        # Load all lines of .env
        with open(".env", "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith("GEMINI_MODEL="):
                new_lines.append(f"GEMINI_MODEL={working_model}\n")
                updated = True
            else:
                new_lines.append(line)
                
        if not updated:
            new_lines.append(f"GEMINI_MODEL={working_model}\n")
            
        with open(".env", "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        print(f"Successfully updated GEMINI_MODEL in backend/.env to: {working_model}")
    except Exception as e:
        print(f"Failed to update backend/.env file: {e}")

def discover_and_test_models():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    
    print("==================================================")
    print(f"GEMINI_API_KEY loaded: {bool(api_key)}")
    if api_key:
        print(f"key length: {len(api_key)}")
    print("==================================================")
    
    if not api_key:
        print("No GEMINI_API_KEY found in environment.")
        return

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
    except ImportError:
        print("google-generativeai SDK is not installed.")
        return

    available_models = []
    print("Available generateContent models:")
    try:
        models_list = genai.list_models()
        for m in models_list:
            try:
                # Check for generateContent support safely
                methods = getattr(m, 'supported_generation_methods', [])
                if any('generateContent' in method for method in methods):
                    available_models.append(m.name)
                    print(f"* {m.name}")
            except Exception as e:
                # Skip deprecated or missing field entries safely
                logger.warning("Skipping model entry due to error: %s", e)
                continue
    except Exception as e:
        print(f"Failed to retrieve models list from API: {e}")
        return

    if not available_models:
        print("No generateContent Gemini models available for this API key.")
        return

    # Determine candidates in order
    def clean_model_name(name: str) -> str:
        if name.startswith("models/"):
            return name[7:]
        return name

    normalized_available = {clean_model_name(m): m for m in available_models}

    candidates = []
    # 1. model from GEMINI_MODEL if provided
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    if env_model:
        # Check both raw and with models/ prefix
        clean_env = clean_model_name(env_model)
        if clean_env in normalized_available:
            candidates.append(normalized_available[clean_env])
        else:
            candidates.append(env_model)
        
    # 2. Preferred ones
    preferred = [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
        "gemini-flash-latest"
    ]
    for p in preferred:
        if p in normalized_available:
            full_name = normalized_available[p]
            if full_name not in candidates:
                candidates.append(full_name)
                
    # 3. Any other available model
    for m in available_models:
        if m not in candidates:
            candidates.append(m)

    print("\nStarting connectivity tests on candidates...")
    tested_models = []
    failed_models = []
    working_model = None

    for model_name in candidates:
        print(f"Testing model: {model_name} ...")
        tested_models.append(model_name)
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("صرف اردو میں ایک مختصر جواب دیں: ٹیسٹ کامیاب")
            text = response.text if response and hasattr(response, "text") else ""
            if text and text.strip():
                print(f"-> SUCCESS! Response: {text.strip()}")
                working_model = model_name
                break
            else:
                print("-> FAILED: Empty response")
                failed_models.append((model_name, "Empty response"))
        except Exception as e:
            print(f"-> FAILED with error: {e}")
            failed_models.append((model_name, str(e)))

    print("\n==================================================")
    print("SUMMARY OF TESTS")
    print("==================================================")
    print(f"Available models: {len(available_models)}")
    print(f"Tested models count: {len(tested_models)}")
    print(f"Failed models count: {len(failed_models)}")
    for fm, reason in failed_models:
        print(f"  * {fm}: {reason}")
    print(f"Working model: {working_model}")
    print("==================================================")

    if working_model:
        update_dotenv_model(working_model)

if __name__ == "__main__":
    discover_and_test_models()
