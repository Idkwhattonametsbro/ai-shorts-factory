import os, sys, json, time, requests, subprocess

OPENROUTER_KEY = os.environ['OPENROUTER_API_KEY']

def log(msg):
    print(f"[LOG] {msg}")
def die(msg):
    print(f"[ERROR] {msg}")
    sys.exit(1)

# ============================================
# STEP 1: Generate script via OpenRouter (free)
# ============================================
log("Step 1: Generating script with OpenRouter (free models)...")
prompt = (
    "Identify the #1 viral topic on YouTube Shorts right now. "
    "Write a 30-60 second vertical video script about it. "
    "Make it attention-grabbing from the first second. "
    "Break it into 5 short scenes. For each scene, also describe "
    "a visual image that should appear. "
    "Format your response as JSON with fields: 'topic', 'scenes' (array of "
    "objects with 'narration' and 'visual_description'). "
    "Return ONLY valid JSON, no other text."
)

script_data = None
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
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": 800,
            "response_format": {"type": "json_object"}
        },
        timeout=60
    )
    
    if resp.status_code == 200:
        raw = resp.json()['choices'][0]['message']['content']
        script_data = json.loads(raw)
        log(f"Topic: {script_data.get('topic', 'Unknown')}")
        log(f"Scenes: {len(script_data.get('scenes', []))}")
    else:
        die(f"OpenRouter returned {resp.status_code}: {resp.text[:300]}")
except Exception as e:
    die(f"OpenRouter error: {e}")

if not script_data or not script_data.get('scenes'):
    die("Invalid script data")

# ============================================
# STEP 2: Generate AI images for each scene
# ============================================
log("Step 2: Generating AI images with Pollinations.ai...")

for i, scene in enumerate(script_data['scenes']):
    visual = scene.get('visual_description', 'viral YouTube Short background')
    img_prompt = f"Vertical 9:16 YouTube Short background, cinematic, viral style, high quality. {visual}"
    
    try:
        img_url = "https://image.pollinations.ai/prompt/" + requests.utils.quote(img_prompt)
        img_resp = requests.get(img_url, params={"width": 1080, "height": 1920}, timeout=60)
        
        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
            with open(f"scene_{i:02d}.jpg", "wb") as f:
                f.write(img_resp.content)
            log(f"Scene {i+1} image generated ({len(img_resp.content)} bytes)")
        else:
            die(f"Image gen failed for scene {i+1}: status {img_resp.status_code}")
    except Exception as e:
        die(f"Image gen error scene {i+1}: {e}")

# ============================================
# STEP 3: Generate voiceover with Edge-TTS
# ============================================
log("Step 3: Generating voiceover...")
full_script = "\n".join([s['narration'] for s in script_data['scenes']])

try:
    subprocess.run([
        "edge-tts", "--text", full_script,
        "--voice", "en-US-JennyNeural",
        "--write-media", "audio.mp3"
    ], check=True)
    log("Voiceover generated successfully")
except Exception as e:
    die(f"TTS error: {e}")

# ============================================
# STEP 4: Assemble video with FFmpeg
# ============================================
log("Step 4: Assembling final video with FFmpeg...")

# Get audio duration
import subprocess as sp
result = sp.run([
    "ffprobe", "-v", "error", "-show_entries",
    "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
    "audio.mp3"
], capture_output=True, text=True)
audio_duration = float(result.stdout.strip())
scene_duration = audio_duration / len(script_data['scenes'])
log(f"Audio: {audio_duration:.1f}s, {len(script_data['scenes'])} scenes, {scene_duration:.1f}s each")

# Build FFmpeg filter complex for transitions
input_args = []
filter_parts = []
concat_parts = []
for i in range(len(script_data['scenes'])):
    input_args.extend(["-loop", "1", "-t", str(scene_duration), "-i", f"scene_{i:02d}.jpg"])
    filter_parts.append(
        f"[{i+1}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,zoompan=z='min(zoom+0.001,1.2)':x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':d={int(scene_duration*30)}:s=1080x1920,"
        f"fade=t=in:st=0:d=0.3:fade=t=out:st={scene_duration-0.3}:d=0.3[v{i}]"
    )
    concat_parts.append(f"[v{i}]")

concat_filter = f"{''.join(concat_parts)}concat=n={len(script_data['scenes'])}:v=1:a=0[vout]"

ffmpeg_cmd = [
    "ffmpeg", "-y",
    *input_args,
    "-i", "audio.mp3",
    "-filter_complex", ";".join(filter_parts) + ";" + concat_filter,
    "-map", "[vout]", "-map", f"{len(script_data['scenes'])+1}:a",
    "-t", str(audio_duration),
    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
    "-c:a", "aac", "-b:a", "128k",
    "-pix_fmt", "yuv420p",
    "-shortest",
    "output.mp4"
]

try:
    subprocess.run(ffmpeg_cmd, check=True)
    log("Video assembled successfully!")
except Exception as e:
    die(f"FFmpeg error: {e}")

log("SUCCESS: output.mp4 is ready!")
print("::notice title=Video Generated::Your AI Short with AI-generated visuals is ready!")
