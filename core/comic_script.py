import os
import base64
import json
import requests

def load_dotenv():
    """Reads .env file from project root if present and populates os.environ."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k:
                        os.environ[k] = v

# Auto load .env on module import
load_dotenv()

def encode_image_base64(image_path):
    """Reads an image file and encodes it to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def get_mime_type(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        return 'image/jpeg'
    elif ext == '.png':
        return 'image/png'
    elif ext == '.webp':
        return 'image/webp'
    return 'image/jpeg'

MODEL_CANDIDATES = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite"
]

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "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")

def call_openrouter_vision(system_instruction, mime_type, base64_data, openrouter_key=OPENROUTER_KEY):
    """Fallback vision call using OpenRouter API."""
    if not openrouter_key:
        return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json"
    }
    data_url = f"data:{mime_type};base64,{base64_data}"
    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": system_instruction},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ],
        "response_format": {"type": "json_object"}
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25)
        if res.status_code == 200:
            res_json = res.json()
            content = res_json['choices'][0]['message']['content']
            parsed = json.loads(content)
            print("  🌐 OpenRouter Vision script generated successfully.")
            return parsed
    except Exception as e:
        print(f"  ⚠️ OpenRouter Vision fallback error: {e}")
    return None

def generate_script_for_page(image_path, page_num, total_pages, ocr_text="", api_key=None, custom_prompt=None, mode="manhwa"):
    """
    Generates a narrator recap script for a comic/manhwa page using OCR text + Gemini/OpenRouter Vision API.
    Returns a dict with {'narrator_text': str, 'page_summary': str}.
    """
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    mime_type = get_mime_type(image_path)
    base64_data = encode_image_base64(image_path)

    ocr_context = f"\nEXTRACTED OCR DIALOGUE FROM SPEECH BUBBLES:\n\"{ocr_text}\"\n" if ocr_text else ""

    if mode == "manhwa":
        system_instruction = (
            "You are a high-energy, hype Manhwa / Webtoon recap narrator (Solo Leveling style). "
            f"{ocr_context}"
            "Analyze the visual panel, character expressions, power aura, dialogue, and fight action in this Manhwa frame image. "
            "Incorporate the extracted dialogue into a fast-paced, intense 2 to 3 sentence narrator script. "
            "Do NOT include stage directions or markdown formatting in narrator_text. "
            "Return ONLY a JSON object with two fields: 'narrator_text' and 'page_summary'."
        )
    else:
        system_instruction = (
            "You are an energetic, dramatic YouTube Comic recap narrator. "
            f"{ocr_context}"
            "Analyze the visual panels, action, emotions, and dialogue in this comic page image. "
            "Use the extracted OCR dialogue to write an engaging 2 to 3 sentence recap narrator script. "
            "Return ONLY a JSON object with two fields: 'narrator_text' and 'page_summary'."
        )

    if custom_prompt:
        system_instruction += f"\nAdditional Context / Style Instructions: {custom_prompt}"

    # 1. Try OpenRouter Vision if key present (fastest & high quota)
    if OPENROUTER_KEY:
        openrouter_res = call_openrouter_vision(system_instruction, mime_type, base64_data)
        if openrouter_res and openrouter_res.get("narrator_text"):
            narrator_text = openrouter_res.get("narrator_text", "").strip()
            print(f"🌐 OpenRouter Vision Script [Panel {page_num}/{total_pages}]: \"{narrator_text}\"", flush=True)
            return openrouter_res

    # 2. Try Gemini Vision candidates
    if api_key:
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_instruction},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64_data
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "response_mime_type": "application/json"
            }
        }

        for model in MODEL_CANDIDATES:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text_resp = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        parsed = json.loads(text_resp)
                        narrator_text = parsed.get("narrator_text", "").strip()
                        summary = parsed.get("page_summary", "").strip()
                        if narrator_text:
                            print(f"🤖 Gemini Vision ({model}) Script [Panel {page_num}/{total_pages}]: \"{narrator_text}\"")
                            return {"narrator_text": narrator_text, "page_summary": summary}
                elif res.status_code in (429, 404):
                    pass
            except Exception:
                pass

    # 3. Dynamic Narrative Fallback
    fallback_narrative = (
        f"The intensity mounts on panel {page_num} as Seonwoo steps forward into the unknown!"
        if not ocr_text else
        f"Kim Seonwoo reacts to the unfolding crisis: \"{ocr_text}\". The tension reaches a boiling point!"
    )
    return {
        "narrator_text": fallback_narrative,
        "page_summary": f"Panel {page_num} visual action."
    }
