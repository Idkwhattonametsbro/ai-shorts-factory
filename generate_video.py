import os, sys, json, time, requests, subprocess

GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '')

def log(msg):
    print(f"[LOG] {msg}")
def die(msg):
    print(f"[ERROR] {msg}")
    sys.exit(1)

# ============================================
# STEP 1: Generate script (Gemini → OpenRouter → Pollinations)
# ============================================
log("Step 1: Generating script...")
prompt = (
    "Identify the #1 viral topic on YouTube Shorts right now. "
    "Write a 30-60 second vertical video script about it. "
    "Make it attention-grabbing from the first second. "
    "Return ONLY the script text, no explanations, no markdown."
)

script = None

# --- Attempt 1: Gemini 1.5 Flash (1,500 req/day, stable) ---
if GEMINI_KEY:
    log("Trying Gemini 1.5 Flash...")
    try:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.9, "maxOutputTokens": 500}
            },
            headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
            timeout=30
        )
        if resp.status_code == 200:
            script = resp.json()['candidates'][0]['content']['parts'][0]['text']
            log(f"Gemini script ({len(script)} chars): {script[:120]}...")
        elif resp.status_code == 429:
            log("Gemini rate limited, falling back...")
        else:
            log(f"Gemini returned {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        log(f"Gemini error: {e}")

# --- Attempt 2: OpenRouter with specific free models + retry ---
if not script and OPENROUTER_KEY:
    log("Trying OpenRouter with specific free models...")
    
    # Specific free models known to be reliable (May 2026)
    free_models = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-super:free",
        "openai/gpt-oss-120b:free"
    ]
    
    for model in free_models:
        log(f"Trying model: {model}...")
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com",
                    "X-Title": "AI Shorts Factory"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.9,
                    "max_tokens": 500
                },
                timeout=30
            )
            
            if resp.status_code == 200:
                script = resp.json()['choices'][0]['message']['content']
                log(f"OpenRouter script via {model} ({len(script)} chars)")
                break
            elif resp.status_code == 429:
                log(f"Model {model} rate limited, trying next...")
                time.sleep(2)  # brief pause before next attempt
            else:
                log(f"Model {model} returned {resp.status_code}")
        except Exception as e:
            log(f"Model {model} error: {e}")
            time.sleep(1)

# --- Attempt 3: Pollinations.ai (no key needed) ---
if not script:
    log("Falling back to Pollinations.ai text generation...")
    try:
        resp = requests.get(
            "https://gen.pollinations.ai/text/" + requests.utils.quote(prompt),
            timeout=60
        )
        if resp.status_code == 200 and len(resp.text) > 50:
            script = resp.text.strip()
            log(f"Pollinations script ({len(script)} chars)")
    except Exception as e:
        die(f"All text generators failed: {e}")

if not script:
    die("No script generated from any source")

# ============================================
# STEP 2: Generate AI images via Pollinations.ai
# ============================================
log("Step 2: Generating AI background image...")
img_prompt = "Vertical 9:16 YouTube Short background, dynamic, colorful, viral style. " + script[:100]

try:
    img_url = "https://image.pollinations.ai/prompt/" + requests.utils.quote(img_prompt)
    img_resp = requests.get(img_url, params={"width": 1080, "height": 1920}, timeout=60)
    
    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
        with open("background.jpg", "wb") as f:
            f.write(img_resp.content)
        log(f"AI background image generated ({len(img_resp.content)} bytes)")
    else:
        die(f"Image generation failed: status {img_resp.status_code}")
except Exception as e:
    die(f"Image generation error: {e}")

# ============================================
# STEP 3: Generate voiceover via Edge-TTS
# ============================================
log("Step 3: Generating voiceover...")
try:
    subprocess.run([
        "edge-tts", "--text", script,
        "--voice", "en-US-JennyNeural",
        "--write-media", "audio.mp3"
    ], check=True)
    log("Voiceover generated successfully")
except Exception as e:
    die(f"TTS error: {e}")

# ============================================
# STEP 4: Assemble video with FFmpeg
# ============================================
log("Step 4: Assembling final video...")
try:
    # Get audio duration for timing
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
        "audio.mp3"
    ], capture_output=True, text=True)
    audio_duration = float(result.stdout.strip())
    log(f"Audio duration: {audio_duration:.1f}s")
    
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", "background.jpg",
        "-i", "audio.mp3",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-t", str(audio_duration),
        "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        "output.mp4"
    ], check=True)
    log("Video assembled successfully!")
except Exception as e:
    die(f"FFmpeg error: {e}")

log("SUCCESS: output.mp4 is ready!")
print("::notice title=Video Generated::Your AI Short is ready! Download from Releases.")
