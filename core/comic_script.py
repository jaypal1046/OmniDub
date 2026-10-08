import os
import re
import base64
import json
from typing import Optional
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

def encode_image_base64(image_path: str) -> str:
    """Reads an image file and encodes it to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def get_mime_type(image_path: str) -> str:
    ext = os.path.splitext(image_path)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        return 'image/jpeg'
    elif ext == '.png':
        return 'image/png'
    elif ext == '.webp':
        return 'image/webp'
    return 'image/jpeg'

def clean_json_response(raw_text: str) -> Optional[dict]:
    """Cleans and extracts JSON object even if enclosed in markdown code fences."""
    text = raw_text.strip()
    if text.startswith("```"):
        # Remove ```json or ``` from start and ``` from end
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        # Try finding outermost { ... }
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None

MODEL_CANDIDATES = ["gemini-3.5-flash-lite"]

_SELECTED_VISION_PROVIDER = None

def get_active_vision_provider() -> str:
    """Use Gemini for vision when configured."""
    global _SELECTED_VISION_PROVIDER
    if _SELECTED_VISION_PROVIDER is not None:
        return _SELECTED_VISION_PROVIDER

    if os.environ.get("GEMINI_API_KEY"):
        print("🤖 [Vision Engine] Active Provider: Google Gemini Vision API (GEMINI_API_KEY).")
        _SELECTED_VISION_PROVIDER = "gemini"
    else:
        print("💡 [Vision Engine] Gemini key unavailable; using heuristic engine.")
        _SELECTED_VISION_PROVIDER = "heuristic"

    return _SELECTED_VISION_PROVIDER


def call_ox_alpha_vision(
    system_instruction: str,
    mime_type: str,
    base64_data: str,
    ox_key: Optional[str] = None,
    base_url: str = "https://oxalpha.run/api/v1",
    model: str = "ox-alpha"
) -> Optional[dict]:
    """Direct vision & story analysis call using Ox Alpha API (3M daily free tokens)."""
    if not ox_key:
        ox_key = os.environ.get("ALPHA_OX_API_KEY") or os.environ.get("OX_ALPHA_API_KEY", "")
    if not ox_key:
        return None

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {ox_key}",
        "Content-Type": "application/json"
    }
    data_url = f"data:{mime_type};base64,{base64_data}"
    payload = {
        "model": model,
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
            parsed = clean_json_response(content)
            if parsed and parsed.get("narrator_text"):
                return parsed
    except Exception:
        pass
    return None


def call_openrouter_vision(system_instruction: str, mime_type: str, base64_data: str, openrouter_key: Optional[str] = None) -> Optional[dict]:
    """Vision call using OpenRouter API."""
    if not openrouter_key:
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
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
            parsed = clean_json_response(content)
            if parsed and parsed.get("narrator_text"):
                return parsed
    except Exception as e:
        print(f"  ⚠️ OpenRouter Vision fallback error: {e}")
    return None


def call_gemini_vision(system_instruction: str, mime_type: str, base64_data: str, api_key: Optional[str] = None) -> Optional[dict]:
    """Direct Google Gemini Vision call."""
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

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
            res = requests.post(url, headers=headers, json=payload, timeout=15)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text_resp = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    parsed = clean_json_response(text_resp)
                    if parsed and parsed.get("narrator_text"):
                        return parsed
        except Exception:
            pass
    return None


def generate_script_for_page(
    image_path: str,
    page_num: int,
    total_pages: int,
    ocr_text: str = "",
    api_key: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    mode: str = "manhwa",
    chapter_context: str = ""
) -> dict:
    """
    Generates a YouTube-style recap narration script using OCR text + Vision API.
    Enforces high-retention storyteller rules: hooks, pacing, emotion, dramatic tension.
    """
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    mime_type = get_mime_type(image_path)
    base64_data = encode_image_base64(image_path)

    ocr_context = f"\nEXTRACTED SPEECH BUBBLES:\n\"{ocr_text}\"\n" if ocr_text else "\n(No speech bubble text detected on this panel)\n"

    is_first = (page_num == 1)
    is_last = (page_num == total_pages)

    if is_first:
        pacing_hint = "This is the OPENING HOOK of the recap video. Start with high suspense and an irresistible hook to captivate YouTube viewers instantly."
    elif is_last:
        pacing_hint = "This is the CLIMAX / CLIFFHANGER of the chapter. Build peak tension and end with suspense."
    else:
        pacing_hint = "Keep the story moving forward naturally with high energy, emotional stakes, and punchy narration."

    system_instruction = (
        "You are an elite, top-tier YouTube Manhwa & Comic Recap Storyteller (like Duskpage / Recap King).\n\n"
        "RECAP NARRATION RULES:\n"
        "1. Do NOT translate or read dialogue bubbles word-for-word robotically. Instead, narrate the unfolding scene, character actions, dramatic reveals, and martial arts / magic power escalation.\n"
        "2. Use fast-paced, engaging conversational English that sounds powerful when read aloud by TTS.\n"
        "3. Write 2 to 3 concise, punchy sentences (approx. 25-45 words total).\n"
        "4. Never invent nonexistent characters or events; ground your narration in the panel art and extracted dialogue.\n"
        "5. Do NOT include stage directions, sound effects in brackets (like [gasp]), or markdown.\n"
        f"{pacing_hint}\n"
        f"{ocr_context}\n"
    )

    if chapter_context:
        system_instruction += f"\nCHAPTER LORE & STORY CONTEXT (From Lore / Status Cards):\n{chapter_context}\n"

    system_instruction += (
        "\nReturn ONLY a JSON object with two fields:\n"
        "- 'narrator_text': The final 2-3 sentence English voiceover script.\n"
        "- 'page_summary': A brief 1-line description of the panel event."
    )

    if custom_prompt:
        system_instruction += f"\nCustom Creator Direction: {custom_prompt}"

    provider = get_active_vision_provider()

    # Try Gemini Vision
    if provider == "gemini" or api_key:
        gemini_res = call_gemini_vision(system_instruction, mime_type, base64_data, api_key=api_key)
        if gemini_res and gemini_res.get("narrator_text"):
            return gemini_res

    # Dynamic Narrative Fallback if API keys unavailable
    if is_first:
        fallback_narrative = "In a world ruled by overwhelming power, everything was about to change for our forgotten protagonist."
    elif ocr_text:
        fallback_narrative = f"The situation turns volatile as words are exchanged: \"{ocr_text[:60]}\". The tension reaches a boiling point!"
    else:
        fallback_narrative = f"With unwavering determination on panel {page_num}, our hero prepares for the monumental battle ahead."

    return {
        "narrator_text": fallback_narrative,
        "page_summary": f"Panel {page_num} visual action."
    }
