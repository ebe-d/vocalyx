import json

cells = []


def to_lines(text):
    return [line + "\n" for line in text.splitlines()]


# Cell 0: Header
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": to_lines("""# 🎙️ Vocalyx — Kaggle Dedicated GPU Server (Git-Synced)

Run the entire **Vocalyx** AI Telephony & Voice Cloning Platform on a free, dedicated **NVIDIA T4 / P100 GPU** on Kaggle with automatic **GitHub sync** and **Kaggle Secrets** support.

### ⚡ Highlights:
- 🔄 **Zero Zip Uploads:** Pulls the latest backend & audio assets directly from your private GitHub repository.
- 🔐 **Zero Hardcoded Secrets:** Reads all API keys cleanly from Kaggle **Add-ons → Secrets**.
- 🚀 **~150x Real-Time TTS:** Supports F5-TTS Flow-Matching, ultra-fast LuxTTS (~0.2s), and Native Indic/English Neural voices.
- ⚡ **5-Second Hot Reload:** Use **Step 7** anytime you push backend changes without reinstalling dependencies.

---

### ⚠️ One-Time Kaggle Setup Before Running:
1. Right sidebar → **Accelerator:** **GPU T4 x2** (or **GPU P100**)
2. Right sidebar → **Internet:** **On**
3. Top bar → **Add-ons → Secrets** (add & toggle ON):
   - `GITHUB_TOKEN` *(only needed if repo is Private; skip if Public)*
   - `GROQ_API_KEY`
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_PHONE_NUMBER`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `NGROK_AUTH_TOKEN`
   - *(Optional)* `WHATSAPP_TO_PHONE`, `GITHUB_REPO`
""")
})

# Cell 1: Step 1 Markdown
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": to_lines("## Step 1: Verify Dedicated GPU Accelerator")
})

# Cell 2: Step 1 Code
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": to_lines("""# Check active GPU accelerator
!nvidia-smi
""")
})

# Cell 3: Step 2 Markdown
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": to_lines("""## Step 2: Install LuxTTS, F5-TTS & Vocalyx Dependencies
Clones LuxTTS and installs diffusion vocoders, F5-TTS, Edge-TTS, and FastAPI dependencies.
""")
})

# Cell 4: Step 2 Code
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": to_lines("""# 1. Clone LuxTTS repository if not already cloned
!if [ ! -d "/kaggle/working/LuxTTS" ]; then git clone https://github.com/ysharma3501/LuxTTS.git /kaggle/working/LuxTTS; fi

# 2. Install LuxTTS & neural vocoder dependencies
!pip install -q -r /kaggle/working/LuxTTS/requirements.txt
!pip install -q git+https://github.com/ysharma3501/LinaCodec.git
!pip install -q piper-phonemize || pip install -q piper_phonemize -f https://k2-fsa.github.io/icefall/piper_phonemize.html || pip install -q piper-phonemize-cross

# 3. Install F5-TTS and Edge-TTS directly
!pip install -q f5-tts edge-tts

# 4. Install Vocalyx server dependencies
!pip install -q fastapi uvicorn[standard] pyngrok twilio groq sqlalchemy sentence-transformers faiss-cpu pypdf python-multipart soundfile

# 5. Verify F5-TTS import
import sys
try:
    import f5_tts
    print("✅ F5-TTS package verified successfully!")
except ImportError:
    print("⚠️ Installing F5-TTS from GitHub repository...")
    !pip install -q git+https://github.com/SWivid/F5-TTS.git

print("✅ All LuxTTS, F5-TTS, and Vocalyx dependencies installed successfully!")
""")
})

# Cell 5: Step 3 Markdown
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": to_lines("""## Step 3: Sync Latest Code & Voice Assets from GitHub
Clones (or hard-pulls) the latest Vocalyx repository from GitHub directly into `/kaggle/working/vocaly`.
""")
})

# Cell 6: Step 3 Code
c6_code = """import os, sys, glob, shutil, subprocess

DEFAULT_REPO = "ebe-d/vocalyx"
dest_dir = "/kaggle/working/vocaly"
backend_dir = os.path.join(dest_dir, "backend")
tts_out = os.path.join(backend_dir, "tts_output")
docs_out = os.path.join(backend_dir, "uploaded_docs")


def _get_secret(name, default=""):
    val = os.environ.get(name, "").strip()
    if val:
        return val
    try:
        from kaggle_secrets import UserSecretsClient
        val = (UserSecretsClient().get_secret(name) or "").strip()
        if val:
            os.environ[name] = val
            return val
    except Exception:
        pass
    return default


github_repo = _get_secret("GITHUB_REPO", DEFAULT_REPO).replace("https://github.com/", "").strip("/")
github_token = _get_secret("GITHUB_TOKEN", "")
branch = _get_secret("GITHUB_BRANCH", "main")

if github_token:
    clone_url = f"https://x-access-token:{github_token}@github.com/{github_repo}.git"
else:
    clone_url = f"https://github.com/{github_repo}.git"

# 1. Clone or pull latest commit from GitHub
if os.path.isdir(os.path.join(dest_dir, ".git")):
    print(f"🔄 Pulling latest changes from github.com/{github_repo} ({branch})...")
    subprocess.run(["git", "-C", dest_dir, "remote", "set-url", "origin", clone_url], check=True)
    subprocess.run(["git", "-C", dest_dir, "fetch", "--depth", "1", "origin", branch], check=True)
    subprocess.run(["git", "-C", dest_dir, "reset", "--hard", f"origin/{branch}"], check=True)
    print("✅ Repository updated to latest commit!")
else:
    if os.path.exists(dest_dir) and not os.listdir(dest_dir):
        shutil.rmtree(dest_dir, ignore_errors=True)
    if not os.path.exists(dest_dir):
        print(f"📦 Cloning github.com/{github_repo} ({branch})...")
        subprocess.run(["git", "clone", "--depth", "1", "-b", branch, clone_url, dest_dir], check=True)
        print("✅ Repository cloned successfully!")
    else:
        print(f"ℹ️ Using existing folder {dest_dir}; syncing via git init/fetch...")
        subprocess.run(["git", "-C", dest_dir, "init"], check=True)
        subprocess.run(["git", "-C", dest_dir, "remote", "remove", "origin"], check=False)
        subprocess.run(["git", "-C", dest_dir, "remote", "add", "origin", clone_url], check=True)
        subprocess.run(["git", "-C", dest_dir, "fetch", "--depth", "1", "origin", branch], check=True)
        subprocess.run(["git", "-C", dest_dir, "reset", "--hard", f"origin/{branch}"], check=True)
        print("✅ Repository synced to latest commit!")

os.makedirs(tts_out, exist_ok=True)
os.makedirs(docs_out, exist_ok=True)

# 2. Ensure voice_clone.mp3 is present in root, backend/, and /kaggle/working/
vclones = [p for p in [
    os.path.join(dest_dir, "voice_clone.mp3"),
    os.path.join(backend_dir, "voice_clone.mp3"),
] + glob.glob("/kaggle/**/voice_clone.mp3", recursive=True) if os.path.exists(p) and os.path.getsize(p) > 0]

if vclones:
    vc_src = vclones[0]
    for target in [
        os.path.join(dest_dir, "voice_clone.mp3"),
        os.path.join(backend_dir, "voice_clone.mp3"),
        "/kaggle/working/voice_clone.mp3",
    ]:
        if os.path.abspath(vc_src) != os.path.abspath(target):
            shutil.copy2(vc_src, target)
    print(f"✅ Voice clone audio synced from: {vc_src}")
else:
    print("⚠️ WARNING: voice_clone.mp3 not found in repo or /kaggle!")

# 3. Sync default_voices into backend/default_voices and backend/tts_output
dv_sources = [
    os.path.join(dest_dir, "default_voices"),
    os.path.join(backend_dir, "default_voices"),
] + glob.glob("/kaggle/input/**/default_voices", recursive=True)

for src in dv_sources:
    files = glob.glob(os.path.join(src, "*.*")) if os.path.isdir(src) else []
    if files:
        for f in files:
            for target_d in [
                os.path.join(dest_dir, "default_voices"),
                os.path.join(backend_dir, "default_voices"),
                tts_out,
                "/kaggle/working/default_voices",
                "/kaggle/working/tts_output",
            ]:
                os.makedirs(target_d, exist_ok=True)
                dst_f = os.path.join(target_d, os.path.basename(f))
                if os.path.abspath(f) != os.path.abspath(dst_f):
                    shutil.copy2(f, dst_f)
        print(f"✅ Synced {len(files)} studio voice files into {tts_out}")
        break

# 4. Generate studio carrier voices only if any are still missing
try:
    for d in [os.path.join(dest_dir, "default_voices"), tts_out]:
        os.makedirs(d, exist_ok=True)
        j_wav = os.path.join(d, "joanna_greeting.wav")
        if not os.path.exists(j_wav):
            j_mp3 = os.path.join(d, "joanna_greeting.mp3")
            os.system(f'{sys.executable} -m edge_tts --text "Hello, thank you for calling Vocalyx! My name is Joanna. How may I assist you today?" --voice en-US-JennyNeural --write-media {j_mp3} >/dev/null 2>&1')
            os.system(f'ffmpeg -y -i {j_mp3} -ar 48000 -ac 1 -c:a pcm_s16le {j_wav} >/dev/null 2>&1')
        f_ref_wav = os.path.join(d, "female_reference.wav")
        if not os.path.exists(f_ref_wav) and os.path.exists(j_wav):
            shutil.copy2(j_wav, f_ref_wav)
        m_wav = os.path.join(d, "matthew_greeting.wav")
        if not os.path.exists(m_wav):
            m_mp3 = os.path.join(d, "matthew_greeting.mp3")
            os.system(f'{sys.executable} -m edge_tts --text "Hello there, thank you for calling Vocalyx. This is Matthew speaking. How can I help you today?" --voice en-US-GuyNeural --write-media {m_mp3} >/dev/null 2>&1')
            os.system(f'ffmpeg -y -i {m_mp3} -ar 48000 -ac 1 -c:a pcm_s16le {m_wav} >/dev/null 2>&1')
        s_wav = os.path.join(d, "sapna_greeting.wav")
        if not os.path.exists(s_wav):
            s_mp3 = os.path.join(d, "sapna_greeting.mp3")
            os.system(f'{sys.executable} -m edge_tts --text "ನಮಸ್ಕಾರ, ವೋಕಲಿಕ್ಸ್‌ಗೆ ಸ್ವಾಗತ! ನನ್ನ ಹೆಸರು ಸ್ವಪ್ನಾ." --voice kn-IN-SapnaNeural --write-media {s_mp3} >/dev/null 2>&1')
            os.system(f'ffmpeg -y -i {s_mp3} -ar 48000 -ac 1 -c:a pcm_s16le {s_wav} >/dev/null 2>&1')
        g_wav = os.path.join(d, "gagan_greeting.wav")
        if not os.path.exists(g_wav):
            g_mp3 = os.path.join(d, "gagan_greeting.mp3")
            os.system(f'{sys.executable} -m edge_tts --text "ನಮಸ್ಕಾರ, ವೋಕಲಿಕ್ಸ್‌ಗೆ ಸ್ವಾಗತ! ನನ್ನ ಹೆಸರು ಗಗನ್." --voice kn-IN-GaganNeural --write-media {g_mp3} >/dev/null 2>&1')
            os.system(f'ffmpeg -y -i {g_mp3} -ar 48000 -ac 1 -c:a pcm_s16le {g_wav} >/dev/null 2>&1')
        sw_wav = os.path.join(d, "swara_greeting.wav")
        if not os.path.exists(sw_wav):
            sw_mp3 = os.path.join(d, "swara_greeting.mp3")
            os.system(f'{sys.executable} -m edge_tts --text "नमस्ते, वोकलिक्स में आपका स्वागत है! मेरा नाम स्वरा है।" --voice hi-IN-SwaraNeural --write-media {sw_mp3} >/dev/null 2>&1')
            os.system(f'ffmpeg -y -i {sw_mp3} -ar 48000 -ac 1 -c:a pcm_s16le {sw_wav} >/dev/null 2>&1')
        md_wav = os.path.join(d, "madhur_greeting.wav")
        if not os.path.exists(md_wav):
            md_mp3 = os.path.join(d, "madhur_greeting.mp3")
            os.system(f'{sys.executable} -m edge_tts --text "नमस्ते, वोकलिक्स में आपका स्वागत है! मेरा नाम मधुर है।" --voice hi-IN-MadhurNeural --write-media {md_mp3} >/dev/null 2>&1')
            os.system(f'ffmpeg -y -i {md_mp3} -ar 48000 -ac 1 -c:a pcm_s16le {md_wav} >/dev/null 2>&1')
except Exception as _v_err:
    print(f"Voice check note: {_v_err}")

print("✅ Step 3 complete: Code & audio assets synced!")
"""
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": to_lines(c6_code)
})

# Cell 7: Step 4 Markdown
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": to_lines("## Step 4: Load Credentials from Kaggle Secrets")
})

# Cell 8: Step 4 Code
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": to_lines("""import os

# Engine defaults
os.environ.setdefault("TWILIO_VOICE_ENGINE", "f5tts")
os.environ.setdefault("TTS_ENGINE", "f5tts")
os.environ.setdefault("WHATSAPP_FROM_PHONE", "whatsapp:+14155238886")

# Load secrets securely from Kaggle Add-ons -> Secrets
secret_keys = [
    "GROQ_API_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "NGROK_AUTH_TOKEN",
    "WHATSAPP_TO_PHONE",
    "SMS_TO_PHONE",
]

try:
    from kaggle_secrets import UserSecretsClient
    _client = UserSecretsClient()
except Exception:
    _client = None

for key in secret_keys:
    val = os.environ.get(key, "").strip()
    if not val and _client is not None:
        try:
            val = (_client.get_secret(key) or "").strip()
            if val:
                os.environ[key] = val
        except Exception:
            pass
    status = "✅ loaded" if os.environ.get(key) else "⚠️ not set"
    print(f"  {key}: {status}")

print("✅ Step 4 complete!")
""")
})

# Cell 9: Step 5 Markdown
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": to_lines("""## Step 5: Pre-Warm Cloned Voice on Dedicated GPU (F5-TTS / LuxTTS)
Loads active TTS engine into GPU VRAM and synthesizes the zero-latency cloned voice telephony files (`prewarmed_greeting.wav`, `prewarmed_reprompt.wav`, `prewarmed_goodbye.wav`).
""")
})

# Cell 10: Step 5 Code
c10_code = """import sys, os, time

for k in ["PYTHONHASHSEED", "PYTHONDEVMODE"]:
    os.environ.pop(k, None)
os.environ["PYTHONHASHSEED"] = "0"

dest_dir = "/kaggle/working/vocaly"
backend_dir = os.path.join(dest_dir, "backend")
os.makedirs(dest_dir, exist_ok=True)
os.chdir(dest_dir)

# Configure module search paths
for p in [dest_dir, backend_dir, "/kaggle/working/LuxTTS", "/kaggle/working"]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from backend import config, tts_engine
tts_engine.config = config

# Ensure F5-TTS is available
try:
    import f5_tts
except ImportError:
    print("📦 Auto-installing f5-tts...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "f5-tts"])

print("🔥 Pre-warming natural cloned voice on dedicated NVIDIA GPU...")
t0 = time.time()
tts_engine.prewarm_engine()
print(f"✅ Pre-warm complete in {time.time() - t0:.2f}s!")
print("✅ Telephony audio ready: prewarmed_greeting.wav, prewarmed_reprompt.wav, prewarmed_goodbye.wav")

# Benchmark dynamic synthesis speed
print("⚡ Testing live dynamic synthesis speed:")
tb = time.time()
test_path = tts_engine.synthesize("Hello, this is Alex calling from Vocalyx. How may I assist you today?")
print(f"🎉 Benchmark complete: Generated cloned speech in {time.time() - tb:.3f}s!")
"""
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": to_lines(c10_code)
})

# Cell 11: Step 6 Markdown
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": to_lines("""## Step 6: Connect Ngrok & Launch Live Vocalyx Server
Starts the public ngrok tunnel on port 8000 and launches the live FastAPI server with real-time logging.
""")
})

# Cell 12: Step 6 Code
c12_code = """import os, sys, time, subprocess
from pyngrok import ngrok

# 1. Clean up any existing server processes
os.system("pkill -9 -f 'main.py' 2>/dev/null")
os.system("pkill -9 -f 'uvicorn' 2>/dev/null")
time.sleep(1)

# 2. Load NGROK_AUTH_TOKEN from env or Kaggle Secrets
NGROK_AUTH_TOKEN = os.environ.get("NGROK_AUTH_TOKEN", "").strip()
if not NGROK_AUTH_TOKEN:
    try:
        from kaggle_secrets import UserSecretsClient
        NGROK_AUTH_TOKEN = (UserSecretsClient().get_secret("NGROK_AUTH_TOKEN") or "").strip()
        if NGROK_AUTH_TOKEN:
            os.environ["NGROK_AUTH_TOKEN"] = NGROK_AUTH_TOKEN
    except Exception:
        pass

if not NGROK_AUTH_TOKEN:
    raise RuntimeError("NGROK_AUTH_TOKEN is missing! Add it to Kaggle Add-ons -> Secrets and run Step 4.")

ngrok.set_auth_token(NGROK_AUTH_TOKEN)
try:
    ngrok.kill()
except Exception:
    pass

tunnel = ngrok.connect(8000)
public_url = str(tunnel.public_url).rstrip("/")
os.environ["PUBLIC_BASE_URL"] = public_url

print("=" * 65)
print("🚀 VOCALYX MULTI-TURN AI TELEPHONY IS LIVE!")
print(f"🌐 PUBLIC BASE URL: {public_url}")
print(f"📞 TWILIO WEBHOOK URL: {public_url}/api/twilio/voice")
print("=" * 65)
print("👉 Paste the PUBLIC BASE URL into your Netlify App Settings as 'Public Server URL'.")

# 3. Launch FastAPI server
for k in ["PYTHONHASHSEED", "PYTHONDEVMODE"]:
    os.environ.pop(k, None)

env_vars = dict(
    os.environ,
    PUBLIC_BASE_URL=public_url,
    PORT="8000",
    PYTHONHASHSEED="0",
    PYTHONPATH="/kaggle/working/vocaly:/kaggle/working/vocaly/backend:/kaggle/working/LuxTTS:/kaggle/working"
)

proc = subprocess.Popen(
    ["python", "-u", "main.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    cwd="/kaggle/working/vocaly",
    env=env_vars
)
time.sleep(2)

try:
    for line in iter(proc.stdout.readline, ""):
        print(line, end="", flush=True)
except KeyboardInterrupt:
    print("Shutting down server...")
    proc.terminate()
    ngrok.kill()
"""
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": to_lines(c12_code)
})

# Cell 13: Step 7 Markdown
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": to_lines("""## Step 7: 5-Second Hot Reload & Restart (After `git push`)
Stop Step 6 (Interrupt) and run this cell whenever you push new backend commits to GitHub — pulls latest code and restarts the server without reinstalling dependencies.
""")
})

# Cell 14: Step 7 Code
c14_code = """import os, glob, shutil, subprocess, time
from pyngrok import ngrok

dest_dir = "/kaggle/working/vocaly"
backend_dir = os.path.join(dest_dir, "backend")
tts_out = os.path.join(backend_dir, "tts_output")

print("🛑 Stopping running server...")
os.system("pkill -9 -f 'main.py' 2>/dev/null")
os.system("pkill -9 -f 'uvicorn' 2>/dev/null")
time.sleep(1)

def _get_secret(name, default=""):
    val = os.environ.get(name, "").strip()
    if val:
        return val
    try:
        from kaggle_secrets import UserSecretsClient
        val = (UserSecretsClient().get_secret(name) or "").strip()
        if val:
            os.environ[name] = val
            return val
    except Exception:
        pass
    return default


branch = _get_secret("GITHUB_BRANCH", "main")
github_repo = _get_secret("GITHUB_REPO", "ebe-d/vocalyx").replace("https://github.com/", "").strip("/")
github_token = _get_secret("GITHUB_TOKEN", "")
if github_token:
    subprocess.run(["git", "-C", dest_dir, "remote", "set-url", "origin", f"https://x-access-token:{github_token}@github.com/{github_repo}.git"], check=True)

print(f"🔄 Fetching latest code from GitHub ({branch})...")
subprocess.run(["git", "-C", dest_dir, "fetch", "--depth", "1", "origin", branch], check=True)
subprocess.run(["git", "-C", dest_dir, "reset", "--hard", f"origin/{branch}"], check=True)

# Re-sync studio voices & voice_clone.mp3
for f in glob.glob(os.path.join(dest_dir, "default_voices", "*.*")):
    os.makedirs(tts_out, exist_ok=True)
    shutil.copy2(f, os.path.join(tts_out, os.path.basename(f)))
vc = os.path.join(dest_dir, "voice_clone.mp3")
if os.path.exists(vc):
    shutil.copy2(vc, os.path.join(backend_dir, "voice_clone.mp3"))

# Refresh ngrok tunnel & relaunch
try:
    ngrok.kill()
except Exception:
    pass

token = _get_secret("NGROK_AUTH_TOKEN", "")
if not token:
    raise RuntimeError("NGROK_AUTH_TOKEN missing! Set it in Kaggle Secrets.")
ngrok.set_auth_token(token)
tunnel = ngrok.connect(8000)
public_url = str(tunnel.public_url).rstrip("/")
os.environ["PUBLIC_BASE_URL"] = public_url

print("=" * 65)
print("♻️ VOCALYX HOT-RELOADED & LIVE!")
print(f"🌐 PUBLIC BASE URL: {public_url}")
print(f"📞 TWILIO WEBHOOK URL: {public_url}/api/twilio/voice")
print("=" * 65)

env_vars = dict(
    os.environ,
    PUBLIC_BASE_URL=public_url,
    PORT="8000",
    PYTHONHASHSEED="0",
    PYTHONPATH="/kaggle/working/vocaly:/kaggle/working/vocaly/backend:/kaggle/working/LuxTTS:/kaggle/working"
)

proc = subprocess.Popen(
    ["python", "-u", "main.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    cwd=dest_dir,
    env=env_vars
)
time.sleep(2)

try:
    for line in iter(proc.stdout.readline, ""):
        print(line, end="", flush=True)
except KeyboardInterrupt:
    print("Shutting down server...")
    proc.terminate()
    ngrok.kill()
"""
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": to_lines(c14_code)
})

nb_data = {
    "cells": cells,
    "metadata": {
        "accelerator": "GPU",
        "colab": {
            "gpuType": "T4",
            "provenance": []
        },
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "codemirror_mode": {
                "name": "ipython",
                "version": 3
            },
            "file_extension": ".py",
            "mimetype": "text/x-python",
            "name": "python",
            "nbconvert_exporter": "python",
            "pygments_lexer": "ipython3",
            "version": "3.10.12"
        }
    },
    "nbformat": 4,
    "nbformat_minor": 0
}

with open("vocalyx_kaggle.ipynb", "w") as f:
    json.dump(nb_data, f, indent=1)

print("Generated Git-synced vocalyx_kaggle.ipynb successfully!")
