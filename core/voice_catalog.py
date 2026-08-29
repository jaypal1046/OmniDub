import os
import sys
import asyncio
import argparse
import edge_tts

# Comprehensive Catalog of Neural Voices grouped by Category & Language
VOICE_CATALOG = {
    "popular_en": {
        "title": "Popular US English Narrators (Top Recommended)",
        "voices": [
            ("en-US-GuyNeural", "Male", "US English", "Deep, clear, professional male narrator"),
            ("en-US-ChristopherNeural", "Male", "US English", "Warm, engaging storytelling male voice"),
            ("en-US-BrianNeural", "Male", "US English", "Casual, energetic male voice"),
            ("en-US-AndrewNeural", "Male", "US English", "Confident, smooth adult male narrator"),
            ("en-US-EricNeural", "Male", "US English", "Authoritative, deep male narrator"),
            ("en-US-RogerNeural", "Male", "US English", "Articulate, polished male speaker"),
            ("en-US-SteffanNeural", "Male", "US English", "Expressive storytelling male voice"),
            ("en-US-JennyNeural", "Female", "US English", "Clear, natural, articulate female narrator"),
            ("en-US-AriaNeural", "Female", "US English", "Expressive, theatrical female voice"),
            ("en-US-AvaNeural", "Female", "US English", "Soft, natural female narrator"),
            ("en-US-EmmaNeural", "Female", "US English", "Modern, friendly female voice"),
            ("en-US-MichelleNeural", "Female", "US English", "Professional, articulate female narrator"),
            ("en-US-AnaNeural", "Female", "US English", "Young, bright female voice"),
        ]
    },
    "multilingual_en": {
        "title": "Multilingual & Regional English Accents (UK, AU, IN, CA)",
        "voices": [
            ("en-US-AndrewMultilingualNeural", "Male", "US English", "Multilingual male voice with high adaptability"),
            ("en-US-BrianMultilingualNeural", "Male", "US English", "Multilingual energetic male voice"),
            ("en-US-AvaMultilingualNeural", "Female", "US English", "Multilingual natural female voice"),
            ("en-US-EmmaMultilingualNeural", "Female", "US English", "Multilingual friendly female voice"),
            ("en-GB-RyanNeural", "Male", "UK English", "Calm, elegant British male narrator"),
            ("en-GB-ThomasNeural", "Male", "UK English", "Formal, traditional British male voice"),
            ("en-GB-SoniaNeural", "Female", "UK English", "Refined, articulate British female narrator"),
            ("en-GB-MaisieNeural", "Female", "UK English", "Warm, youthful British female voice"),
            ("en-GB-LibbyNeural", "Female", "UK English", "Engaging British female storyteller"),
            ("en-AU-WilliamMultilingualNeural", "Male", "AU English", "Australian male narrator"),
            ("en-AU-NatashaNeural", "Female", "AU English", "Australian female narrator"),
            ("en-IN-PrabhatNeural", "Male", "IN English", "Indian English male narrator"),
            ("en-IN-NeerjaExpressiveNeural", "Female", "IN English", "Expressive Indian English female voice"),
            ("en-CA-LiamNeural", "Male", "CA English", "Canadian English male narrator"),
            ("en-CA-ClaraNeural", "Female", "CA English", "Canadian English female narrator"),
        ]
    },
    "chinese_donghua": {
        "title": "Chinese Donghua / Anime / Novel Narrators (Mandarin & Cantonese)",
        "voices": [
            ("zh-CN-YunxiNeural", "Male", "Mandarin", "Hot-blooded anime / donghua male protagonist"),
            ("zh-CN-YunjianNeural", "Male", "Mandarin", "Heroic, passionate male narrator"),
            ("zh-CN-YunyangNeural", "Male", "Mandarin", "Formal, steady documentary male voice"),
            ("zh-CN-XiaoxiaoNeural", "Female", "Mandarin", "Warm, emotional female novel reader"),
            ("zh-CN-XiaoyiNeural", "Female", "Mandarin", "Gentle, soft female narrator"),
            ("zh-CN-YunxiaNeural", "Male", "Mandarin", "Young energetic male voice"),
            ("zh-TW-HsiaoChenNeural", "Female", "Taiwanese", "Standard Traditional Chinese female voice"),
            ("zh-HK-WanLungNeural", "Male", "Cantonese", "Cantonese male narrator"),
            ("zh-HK-HiuGaaiNeural", "Female", "Cantonese", "Cantonese female narrator"),
        ]
    },
    "japanese_anime": {
        "title": "Japanese (Anime / Manga Redubbing)",
        "voices": [
            ("ja-JP-KeitaNeural", "Male", "Japanese", "Anime male protagonist voice"),
            ("ja-JP-NanamiNeural", "Female", "Japanese", "Clear, cute anime female voice"),
        ]
    },
    "korean_manhwa": {
        "title": "Korean (Manhwa / K-Drama Redubbing)",
        "voices": [
            ("ko-KR-HyunsuMultilingualNeural", "Male", "Korean", "Multilingual Korean male voice"),
            ("ko-KR-InJoonNeural", "Male", "Korean", "Calm Korean male narrator"),
            ("ko-KR-SunHiNeural", "Female", "Korean", "Bright, clear Korean female narrator"),
        ]
    },
    "hindi_indian": {
        "title": "Hindi & Indian Regional Voices",
        "voices": [
            ("hi-IN-MadhurNeural", "Male", "Hindi", "Deep, clear Hindi male narrator"),
            ("hi-IN-SwaraNeural", "Female", "Hindi", "Melodious, clear Hindi female narrator"),
            ("ta-IN-ValluvarNeural", "Male", "Tamil", "Tamil male narrator"),
            ("ta-IN-PallaviNeural", "Female", "Tamil", "Tamil female narrator"),
            ("te-IN-MohanNeural", "Male", "Telugu", "Telugu male narrator"),
            ("te-IN-ShrutiNeural", "Female", "Telugu", "Telugu female narrator"),
        ]
    },
    "european_global": {
        "title": "European & Global Languages (Spanish, French, German, Italian, Russian)",
        "voices": [
            ("es-ES-AlvaroNeural", "Male", "Spanish (ES)", "Spanish male narrator"),
            ("es-ES-ElviraNeural", "Female", "Spanish (ES)", "Spanish female narrator"),
            ("es-MX-JorgeNeural", "Male", "Spanish (MX)", "Mexican Spanish male narrator"),
            ("es-MX-DaliaNeural", "Female", "Spanish (MX)", "Mexican Spanish female narrator"),
            ("fr-FR-RemyMultilingualNeural", "Male", "French", "French male narrator"),
            ("fr-FR-VivienneMultilingualNeural", "Female", "French", "French female narrator"),
            ("de-DE-FlorianMultilingualNeural", "Male", "German", "German male narrator"),
            ("de-DE-SeraphinaMultilingualNeural", "Female", "German", "German female narrator"),
            ("it-IT-GiuseppeMultilingualNeural", "Male", "Italian", "Italian male narrator"),
            ("it-IT-IsabellaNeural", "Female", "Italian", "Italian female narrator"),
            ("ru-RU-DmitryNeural", "Male", "Russian", "Russian male narrator"),
            ("ru-RU-SvetlanaNeural", "Female", "Russian", "Russian female narrator"),
        ]
    }
}

# Backwards compatibility flat list
POPULAR_VOICES = VOICE_CATALOG["popular_en"]["voices"]

# Sample texts tuned per voice language/accent
SAMPLE_TEXTS = {
    # English (US)
    "en-US-GuyNeural": "Welcome to the AI recap engine. This is Guy, a deep and professional male narrator.",
    "en-US-ChristopherNeural": "Welcome to the AI recap engine. This is Christopher, a warm storytelling male voice.",
    "en-US-BrianNeural": "Welcome to the AI recap engine. This is Brian, a casual and energetic male voice.",
    "en-US-AndrewNeural": "Welcome to the AI recap engine. This is Andrew, a confident and smooth adult narrator.",
    "en-US-EricNeural": "Welcome to the AI recap engine. This is Eric, an authoritative and deep narrator.",
    "en-US-RogerNeural": "Welcome to the AI recap engine. This is Roger, an articulate and polished speaker.",
    "en-US-SteffanNeural": "Welcome to the AI recap engine. This is Steffan, an expressive story narrator.",
    "en-US-JennyNeural": "Welcome to the AI recap engine. This is Jenny, a clear female narrator.",
    "en-US-AriaNeural": "Welcome to the AI recap engine. This is Aria, an expressive female narrator.",
    "en-US-AvaNeural": "Welcome to the AI recap engine. This is Ava, a natural and smooth female voice.",
    "en-US-EmmaNeural": "Welcome to the AI recap engine. This is Emma, a modern and friendly female voice.",
    "en-US-MichelleNeural": "Welcome to the AI recap engine. This is Michelle, a clear professional speaker.",
    "en-US-AnaNeural": "Welcome to the AI recap engine. This is Ana, a bright young female voice.",

    # English (Multilingual / Regional)
    "en-US-AndrewMultilingualNeural": "Welcome to the AI recap engine. This is Andrew with multilingual capabilities.",
    "en-US-BrianMultilingualNeural": "Welcome to the AI recap engine. This is Brian with multilingual support.",
    "en-US-AvaMultilingualNeural": "Welcome to the AI recap engine. This is Ava with natural multilingual narration.",
    "en-US-EmmaMultilingualNeural": "Welcome to the AI recap engine. This is Emma, a multilingual female voice.",
    "en-GB-RyanNeural": "Welcome to the AI recap engine. This is Ryan, a calm British male voice.",
    "en-GB-ThomasNeural": "Welcome to the AI recap engine. This is Thomas, a formal British narrator.",
    "en-GB-SoniaNeural": "Welcome to the AI recap engine. This is Sonia, a refined British female narrator.",
    "en-GB-MaisieNeural": "Welcome to the AI recap engine. This is Maisie, a warm British female voice.",
    "en-GB-LibbyNeural": "Welcome to the AI recap engine. This is Libby, an engaging British storyteller.",
    "en-AU-WilliamMultilingualNeural": "G'day! This is William, an Australian male narrator for your recap videos.",
    "en-AU-NatashaNeural": "G'day! This is Natasha, an Australian female voice for recap videos.",
    "en-IN-PrabhatNeural": "Namaste! This is Prabhat, an Indian English male voice narrator.",
    "en-IN-NeerjaExpressiveNeural": "Namaste! This is Neerja, an expressive Indian English female voice.",
    "en-CA-LiamNeural": "Hello! This is Liam, a clear Canadian English male narrator.",
    "en-CA-ClaraNeural": "Hello! This is Clara, an articulate Canadian English female narrator.",

    # Chinese
    "zh-CN-YunxiNeural": "欢迎来到国漫配音教程。我是云希，热血动漫男主配音。",
    "zh-CN-YunjianNeural": "欢迎来到国漫配音教程。我是云剑，激昂豪爽的叙事男声。",
    "zh-CN-YunyangNeural": "欢迎来到国漫配音教程。我是云扬，专业稳重的男声旁白。",
    "zh-CN-XiaoxiaoNeural": "欢迎来到国漫配音教程。我是小小，感性温暖的女性小说播音员。",
    "zh-CN-XiaoyiNeural": "欢迎来到国漫配音教程。我是晓伊，温婉柔和的女性旁白。",
    "zh-CN-YunxiaNeural": "欢迎来到国漫配音教程。我是云霞，阳光活力的男声旁白。",
    "zh-TW-HsiaoChenNeural": "歡迎來到配音教學。我是曉陳，標準繁體中文女聲。",
    "zh-HK-WanLungNeural": "歡迎嚟到配音教程。我是雲龍，廣東話男聲旁白。",
    "zh-HK-HiuGaaiNeural": "歡迎嚟到配音教程。我是曉佳，廣東話女聲旁白。",

    # Japanese
    "ja-JP-KeitaNeural": "アニメ吹替へようこそ。私は圭太、男性の熱血主人公ボイスです。",
    "ja-JP-NanamiNeural": "アニメ吹替へようこそ。私は七海、爽やかで可愛い女性ボイスです。",

    # Korean
    "ko-KR-HyunsuMultilingualNeural": "웹툰 및 애니메이션 더빙에 오신 것을 환영합니다. 남성 다국어 성우 현수입니다.",
    "ko-KR-InJoonNeural": "웹툰 및 애니메이션 더빙에 오신 것을 환영합니다. 차분한 남성 내레이터 인준입니다.",
    "ko-KR-SunHiNeural": "웹툰 및 애니메이션 더빙에 오신 것을 환영합니다. 밝고 명확한 여성 성우 선희입니다.",

    # Hindi & Indian Languages
    "hi-IN-MadhurNeural": "एआई वीडियो रीकैप में आपका स्वागत है। मैं मधुर हूँ, एक गंभीर और स्पष्ट हिंदी पुरुष आवाज।",
    "hi-IN-SwaraNeural": "एआई वीडियो रीकैप में आपका स्वागत है। मैं स्वरा हूँ, एक मधुर और स्पष्ट हिंदी महिला आवाज।",
    "ta-IN-ValluvarNeural": "வணக்கம்! AI வீடியோ ரீகேப்பிற்கு வரவேற்கிறோம். நான் வள்ளுவர், தமிழ் ஆண் குரல்.",
    "ta-IN-PallaviNeural": "வணக்கம்! AI வீடியோ ரீகேப்பிற்கு வரவேற்கிறோம். நான் பல்லவி, தமிழ் பெண் குரல்.",
    "te-IN-MohanNeural": "నమస్కారం! AI వీడియో రీక్యాప్‌కు స్వాగతం. నేను మోహన్, తెలుగు పురుష స్వరం.",
    "te-IN-ShrutiNeural": "నమస్కారం! AI వీడియో రీక్యాప్‌కు స్వాగతం. నేను శృతి, తెలుగు స్త్రీ స్వరం.",

    # European
    "es-ES-AlvaroNeural": "Bienvenido al generador de resúmenes de video. Soy Álvaro, voz masculina de España.",
    "es-ES-ElviraNeural": "Bienvenido al generador de resúmenes de video. Soy Elvira, voz femenina de España.",
    "es-MX-JorgeNeural": "Bienvenido al generador de resúmenes de video. Soy Jorge, voz masculina de México.",
    "es-MX-DaliaNeural": "Bienvenido al generador de resúmenes de video. Soy Dalia, voz femenina de México.",
    "fr-FR-RemyMultilingualNeural": "Bienvenue dans le générateur de résumés vidéo. Je suis Rémy, voix masculine française.",
    "fr-FR-VivienneMultilingualNeural": "Bienvenue dans le générateur de résumés vidéo. Je suis Vivienne, voix féminine française.",
    "de-DE-FlorianMultilingualNeural": "Willkommen beim KI-Video-Recap-Generator. Ich bin Florian, deutsche Männerstimme.",
    "de-DE-SeraphinaMultilingualNeural": "Willkommen beim KI-Video-Recap-Generator. Ich bin Seraphina, deutsche Frauenstimme.",
    "it-IT-GiuseppeMultilingualNeural": "Benvenuto nel generatore di recap video. Sono Giuseppe, voce maschile italiana.",
    "it-IT-IsabellaNeural": "Benvenuto nel generatore di recap video. Sono Isabella, voce femminile italiana.",
    "ru-RU-DmitryNeural": "Добро пожаловать в генератор видеопересказов. Я Дмитрий, мужской дикторский голос.",
    "ru-RU-SvetlanaNeural": "Добро пожаловать в генератор видеопересказов. Я Светлана, женский дикторский голос.",
}

def list_narrator_voices(category_filter=None):
    """Prints a formatted, categorized catalog of neural narration voices."""
    print("=========================================================================")
    print("              FULL MASTER CATALOG OF NEURAL NARRATION VOICES             ")
    print("=========================================================================\n")

    total_count = 0
    for cat_id, cat_info in VOICE_CATALOG.items():
        if category_filter and category_filter.lower() not in [cat_id.lower(), "all"]:
            continue
            
        print(f"--- 🎙️ CATEGORY: {cat_info['title']} ({cat_id}) ---")
        for short_name, gender, locale, desc in cat_info["voices"]:
            print(f"  • Voice: {short_name:<32} | {gender:<6} | {locale:<12} | {desc}")
            total_count += 1
        print()
        
    print(f"Total Voices Displayed: {total_count}")
    print("=========================================================================\n")

def get_voice_category_map():
    """Returns a dictionary mapping each voice name to its category ID."""
    v_map = {}
    for cat_id, cat_info in VOICE_CATALOG.items():
        for short_name, _, _, _ in cat_info["voices"]:
            if short_name not in v_map:
                v_map[short_name] = cat_id
    return v_map

def organize_existing_samples(output_dir="docs/voice_samples"):
    """Moves loose .mp3 sample files in output_dir root into category subfolders."""
    if not os.path.exists(output_dir):
        return
    v_map = get_voice_category_map()
    moved_count = 0
    for f in os.listdir(output_dir):
        if f.endswith(".mp3"):
            voice_name = f[:-4]
            cat_id = v_map.get(voice_name, "other")
            cat_dir = os.path.join(output_dir, cat_id)
            os.makedirs(cat_dir, exist_ok=True)
            src = os.path.join(output_dir, f)
            dst = os.path.join(cat_dir, f)
            try:
                import shutil
                shutil.move(src, dst)
                moved_count += 1
            except Exception as e:
                print(f"Error moving {f}: {e}")
    if moved_count > 0:
        print(f"📁 Organized {moved_count} loose MP3 samples into category subfolders in '{output_dir}'.")

async def _generate_samples_async(output_dir, category_filter=None, max_workers=5):
    os.makedirs(output_dir, exist_ok=True)
    v_map = get_voice_category_map()

    items_to_gen = []
    for cat_id, cat_info in VOICE_CATALOG.items():
        if category_filter and category_filter.lower() not in [cat_id.lower(), "all"]:
            continue
        cat_dir = os.path.join(output_dir, cat_id)
        os.makedirs(cat_dir, exist_ok=True)
        for short_name, _, _, _ in cat_info["voices"]:
            items_to_gen.append((short_name, cat_id, cat_dir))

    print(f"🎙️ Generating MP3 audio voice samples for {len(items_to_gen)} voices into category subfolders...\n")

    semaphore = asyncio.Semaphore(max_workers)

    async def generate_single(voice_name, cat_id, cat_dir):
        text = SAMPLE_TEXTS.get(voice_name, f"Hello, this is {voice_name} speaking.")
        out_path = os.path.join(cat_dir, f"{voice_name}.mp3")
        
        async with semaphore:
            for attempt in range(3):
                try:
                    communicate = edge_tts.Communicate(text, voice_name)
                    await communicate.save(out_path)
                    print(f"  ✅ [{cat_id}] Generated: {os.path.basename(out_path)}")
                    return True
                except Exception as e:
                    if attempt == 2:
                        print(f"  ❌ [{cat_id}] Failed {voice_name}: {e}")
                    await asyncio.sleep(0.5 * (attempt + 1))
        return False

    tasks = [generate_single(v, c_id, c_dir) for v, c_id, c_dir in items_to_gen]
    results = await asyncio.gather(*tasks)
    success_count = sum(1 for r in results if r)
    print(f"\n🎉 Voice sample generation complete! ({success_count}/{len(items_to_gen)} created across category subfolders)")

def generate_voice_samples(output_dir="docs/voice_samples", category_filter=None):
    """Generates sample MP3 audio clips into category subfolders in output_dir."""
    organize_existing_samples(output_dir)
    asyncio.run(_generate_samples_async(output_dir, category_filter=category_filter))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Master Neural Voice Catalog & Audio Sample Generator")
    parser.add_argument("--list", action="store_true", help="List all cataloged voices by category")
    parser.add_argument("--generate", action="store_true", help="Generate MP3 voice samples in docs/voice_samples/")
    parser.add_argument("--organize", action="store_true", help="Organize loose MP3 files into category subfolders")
    parser.add_argument("--category", default=None, help="Filter by specific category (e.g. popular_en, chinese_donghua, japanese_anime, etc.)")
    parser.add_argument("--output-dir", default="docs/voice_samples", help="Directory to save MP3 voice samples")

    args = parser.parse_args()

    if args.organize:
        organize_existing_samples(output_dir=args.output_dir)
    elif args.generate:
        generate_voice_samples(output_dir=args.output_dir, category_filter=args.category)
    else:
        list_narrator_voices(category_filter=args.category)
