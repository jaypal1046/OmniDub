import os
import re
import json
import time
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

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
AIML_API_KEY = os.environ.get("AIMLAPI", os.environ.get("AIML_API_KEY", ""))
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "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")

def call_llm_text(prompt, system_instruction=""):
    """
    Unified LLM call supporting Google Gemini API, AIML API, and OpenRouter fallback.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY", GEMINI_API_KEY)
    aiml_key = os.environ.get("AIMLAPI", os.environ.get("AIML_API_KEY", AIML_API_KEY))
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", OPENROUTER_KEY)

    # 1. Direct Gemini API call if key is present
    if gemini_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        payload = {
            "contents": [{
                "parts": [{"text": f"{system_instruction}\n\n{prompt}" if system_instruction else prompt}]
            }],
            "generationConfig": {
                "temperature": 0.3
            }
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip()
            else:
                print(f"⚠️ Direct Gemini API status {res.status_code}: {res.text[:100]}")
        except Exception as e:
            print(f"⚠️ Gemini API direct call error: {e}")

    # 2. AIML API call if key is present (tries stealth/ox-alpha then google/gemini-2.5-flash)
    if aiml_key:
        url = "https://api.aimlapi.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {aiml_key.strip()}",
            "Content-Type": "application/json"
        }
        aiml_models = ["stealth/ox-alpha", "google/gemini-2.5-flash", "gemini-2.5-flash"]
        for model in aiml_models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_instruction or "You are a professional video dubbing translator."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3
            }
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=30)
                if res.status_code == 200:
                    data = res.json()
                    text = data["choices"][0]["message"]["content"]
                    return text.strip()
                else:
                    print(f"⚠️ AIML API ({model}) status {res.status_code}: {res.text[:100]}")
            except Exception as e:
                print(f"⚠️ AIML API ({model}) call error: {e}")

    # 3. Fallback to OpenRouter API
    if openrouter_key:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "google/gemini-2.5-flash",
            "messages": [
                {"role": "system", "content": system_instruction or "You are a professional video dubbing translator."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                text = data["choices"][0]["message"]["content"]
                return text.strip()
            else:
                print(f"⚠️ OpenRouter API status {res.status_code}: {res.text[:100]}")
        except Exception as e:
            print(f"⚠️ OpenRouter call error: {e}")

    return None

def translate_subtitles_with_gemini(sub_file_path, output_vtt_path, target_lang="Hindi", source_lang="Chinese", batch_size=20):
    """
    Reads original VTT/SRT subtitles, calculates timing budgets, and calls Gemini
    to perform timing-aware, dubbing-optimized translations.
    """
    from core.tts_engine import parse_single_sub_file, ms_to_vtt_timestamp

    entries = parse_single_sub_file(sub_file_path)
    if not entries:
        print(f"⚠️ No subtitle cues found in {sub_file_path}")
        return output_vtt_path

    print(f"\n🤖 Translating {len(entries)} subtitle cues into {target_lang} using Gemini (Timing-Aware Dubbing Engine)...")

    translated_entries = []

    # Process in batches for efficient LLM context and faster translation
    for i in range(0, len(entries), batch_size):
        batch = entries[i:i + batch_size]
        
        items_payload = []
        for idx, item in enumerate(batch):
            dur_sec = round(item["duration_ms"] / 1000.0, 2)
            # Estimate word count limit for target language (~3 words per second for Hindi/English)
            word_limit = max(int(dur_sec * 3.0), 3)
            items_payload.append({
                "id": idx + 1,
                "text": item["text"],
                "duration_sec": dur_sec,
                "target_word_limit": word_limit
            })

        system_prompt = (
            f"You are a master professional film, movie, and anime dubbing translator and dialogue writer.\n"
            f"Your task is to translate speech from {source_lang} into natural, high-performance {target_lang} for voice actors/TTS dubbing.\n\n"
            f"CRITICAL PROFESSIONAL DUBBING CONSTRAINTS & RULES:\n"
            f"1. TRANSLATE FOR TIMING (DURATION BUDGET):\n"
            f"   - Do NOT produce literal or word-for-word translation if it becomes too long!\n"
            f"   - Keep each sentence strictly within its 'duration_sec' and 'target_word_limit'.\n"
            f"   - Shorten and adapt phrasing so it can be spoken comfortably at a natural 1.0x speech rate.\n"
            f"2. PRESERVE DRAMATIC PAUSES & PERFORMANCE:\n"
            f"   - Use '...' for dramatic pauses when the original sentence has hesitations or emotional breaks.\n"
            f"3. DUBBING WRITER STYLE:\n"
            f"   - Preserve core character emotion, tone, and intent while trimming redundant/filler words.\n"
            f"4. STRICT OUTPUT FORMAT:\n"
            f"   - Output MUST be a valid JSON array of objects with exact keys 'id' and 'translated_text'.\n"
            f"   - Example: [{{\"id\": 1, \"translated_text\": \"...\"}}]\n"
        )

        user_prompt = f"Translate these cues to {target_lang} for dubbing timing:\n" + json.dumps(items_payload, ensure_ascii=False, indent=2)

        raw_response = call_llm_text(user_prompt, system_prompt)
        
        parsed_batch = {}
        if raw_response:
            try:
                # Clean markdown code block if present
                clean_resp = re.sub(r"^```json\s*", "", raw_response, flags=re.MULTILINE)
                clean_resp = re.sub(r"```$", "", clean_resp, flags=re.MULTILINE).strip()
                res_list = json.loads(clean_resp)
                for res_item in res_list:
                    parsed_batch[res_item["id"]] = res_item["translated_text"]
            except Exception as e:
                print(f"⚠️ Failed to parse Gemini response JSON batch: {e}")

        for idx, item in enumerate(batch):
            cue_id = idx + 1
            trans_text = parsed_batch.get(cue_id, item["text"])
            item_copy = dict(item)
            item_copy["text"] = trans_text
            translated_entries.append(item_copy)

        print(f"  ✓ Processed cues {i+1} to {min(i+batch_size, len(entries))}/{len(entries)}")

    # Write output VTT
    os.makedirs(os.path.dirname(os.path.abspath(output_vtt_path)), exist_ok=True)
    lines = ["WEBVTT\n"]
    for entry in translated_entries:
        start_ts = ms_to_vtt_timestamp(entry["start_ms"])
        end_ts = ms_to_vtt_timestamp(entry["end_ms"])
        lines.append(f"\n{start_ts} --> {end_ts}\n{entry['text']}\n")

    with open(output_vtt_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"🎉 Timing-aware {target_lang} subtitles exported to: {output_vtt_path}")
    return output_vtt_path

def rewrite_cue_for_duration(original_text, target_duration_sec, target_lang="Hindi"):
    """
    Duration Controller rewrite function:
    When generated TTS audio exceeds the target duration by >10%, Gemini rewrites and shortens the sentence.
    """
    word_budget = max(int(target_duration_sec * 2.8), 2)
    
    system_prompt = (
        f"You are a professional audio dubbing editor.\n"
        f"The current sentence is TOO LONG to fit in the video audio window ({target_duration_sec:.1f} seconds).\n"
        f"Shorten the sentence in {target_lang} so it can be spoken in under {target_duration_sec:.1f} seconds (approx max {word_budget} words).\n"
        f"Keep the original core meaning and emotion, but make it concise.\n"
        f"Return ONLY the shortened {target_lang} sentence text."
    )

    user_prompt = f"Sentence: \"{original_text}\"\nTarget Duration: {target_duration_sec:.1f} seconds."

    rewritten = call_llm_text(user_prompt, system_prompt)
    if rewritten:
        # Strip quotes or markdown formatting
        rewritten = rewritten.strip().strip('"').strip("'").strip()
        return rewritten
    return original_text
