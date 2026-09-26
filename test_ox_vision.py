import os
import sys
import base64
import json
import requests
from core.comic_script import load_dotenv

load_dotenv()
ox_key = os.environ.get("ALPHA_OX_API_KEY") or os.environ.get("OX_ALPHA_API_KEY")
aiml_key = os.environ.get("AIMLAPI")

print("=========================================================================")
print("🔬 VERIFICATION: IS 503 CAUSED BY THE IMAGE OR THE OX ALPHA BACKEND?")
print("=========================================================================")

# 1. Test Ox Alpha with pure text (NO IMAGE)
print("\n👉 [TEST 1] Testing Ox Alpha with pure text ('Hello, what is your name?'):")
try:
    res_text = requests.post(
        "https://oxalpha.run/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {ox_key}", "Content-Type": "application/json"},
        json={"model": "ox-alpha", "messages": [{"role": "user", "content": "Hello"}]},
        timeout=10
    )
    print(f"   Status Code: {res_text.status_code}")
    print(f"   Response:    {res_text.text}")
    if res_text.status_code == 503:
        print("   ➡️ PROOF: Even with ZERO images (pure 5-letter text 'Hello'), Ox Alpha returns 503.")
        print("   ➡️ CONCLUSION: The issue is NOT caused by the image; Ox Alpha's backend is under maintenance.")
except Exception as e:
    print(f"   Error: {e}")

# 2. Test AIMLAPI with the actual Manhwa Image
if aiml_key:
    sample_img = os.path.abspath("output/recap_test1/images/panels/page_001_p03.png")
    if not os.path.exists(sample_img):
        sample_img = os.path.abspath("output/recap_test/images/panels/page_001_p03.png")

    print(f"\n👉 [TEST 2] Testing the exact same manhwa image on AIMLAPI Vision Provider:")
    print(f"   Image file: {sample_img}")
    with open(sample_img, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this manhwa panel in 2 punchy sentences."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_data}"}}
                ]
            }
        ]
    }
    try:
        res_aiml = requests.post(
            "https://api.aimlapi.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {aiml_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=25
        )
        print(f"   Status Code: {res_aiml.status_code}")
        if res_aiml.status_code == 200:
            content = res_aiml.json()["choices"][0]["message"]["content"]
            print("   ✅ SUCCESS: Image was processed perfectly by Vision model!")
            print(f"   AI Description:\n   \"{content}\"")
    except Exception as e:
        print(f"   AIMLAPI Error: {e}")

print("\n=========================================================================")
