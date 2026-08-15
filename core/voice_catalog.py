import os
import asyncio
import edge_tts

POPULAR_VOICES = [
    ("en-US-GuyNeural", "Male", "US English", "Deep, clear, professional male narrator"),
    ("en-US-ChristopherNeural", "Male", "US English", "Warm, engaging storytelling male voice"),
    ("en-US-BrianNeural", "Male", "US English", "Casual, energetic male voice"),
    ("en-US-JennyNeural", "Female", "US English", "Clear, natural, articulate female narrator"),
    ("en-US-AriaNeural", "Female", "US English", "Expressive, theatrical female voice"),
    ("en-US-AnaNeural", "Female", "US English", "Young, bright female voice"),
    ("en-GB-RyanNeural", "Male", "UK English", "British male narrator, calm & elegant"),
    ("en-GB-SoniaNeural", "Female", "UK English", "British female narrator, clear & refined"),
    ("zh-CN-YunxiNeural", "Male", "Mandarin", "Lively anime / donghua male voice"),
    ("zh-CN-XiaoxiaoNeural", "Female", "Mandarin", "Warm, emotional female novel reader"),
]

def list_narrator_voices():
    """Prints a formatted table of recommended narration voices."""
    print("=========================================================================")
    print("                TOP RECOMMENDED NEURAL NARRATION VOICES                 ")
    print("=========================================================================\n")
    
    for short_name, gender, locale, desc in POPULAR_VOICES:
        print(f"Voice: {short_name:<26} | {gender:<6} | {locale:<10} | {desc}")

async def _generate_samples_async(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Generating audio voice samples in {output_dir} ...\n")
    
    sample_texts = [
        ("en-US-GuyNeural", "Welcome to the anime redub tutorial. This is Guy, a deep male voice."),
        ("en-US-ChristopherNeural", "Welcome to the anime redub tutorial. This is Christopher, a warm story narrator."),
        ("en-US-BrianNeural", "Welcome to the anime redub tutorial. This is Brian, an energetic male voice."),
        ("en-US-JennyNeural", "Welcome to the anime redub tutorial. This is Jenny, a clear female narrator."),
        ("en-US-AriaNeural", "Welcome to the anime redub tutorial. This is Aria, an expressive female voice."),
        ("en-GB-RyanNeural", "Welcome to the anime redub tutorial. This is Ryan, a British male voice."),
        ("zh-CN-YunxiNeural", "欢迎来到国漫配音教程。我是云希，热血动漫男声。")
    ]

    for voice_name, text in sample_texts:
        out_path = os.path.join(output_dir, f"{voice_name}.mp3")
        print(f"Generating sample for {voice_name}...")
        communicate = edge_tts.Communicate(text, voice_name)
        await communicate.save(out_path)
        print(f" -> Saved: {out_path}")

    print("\nAll audio samples generated successfully!")

def generate_voice_samples(output_dir="docs/voice_samples"):
    """Generates sample MP3 audio clips into output_dir."""
    asyncio.run(_generate_samples_async(output_dir))

if __name__ == "__main__":
    list_narrator_voices()
