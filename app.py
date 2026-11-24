"""
Hugging Face Spaces Entrypoint for Vocalyx AI Telephony Backend.
Uses native Gradio demo.launch() with ZeroGPU hardware allocation.
Seamlessly attaches all FastAPI REST & Telephony routes to Gradio's internal App.
"""
import os
import sys
import subprocess

# 1. Strictly disable Gradio 5 Server-Side Rendering (SSR) to prevent port 7861 conflicts
os.environ["GRADIO_SSR_MODE"] = "False"

# 2. Install chatterbox-tts and audio dependencies once at startup
if not os.path.exists("/tmp/.chatterbox_installed"):
    for pkg in ["librosa", "omegaconf", "chatterbox-tts"]:
        try:
            mod_name = "chatterbox" if pkg == "chatterbox-tts" else pkg
            __import__(mod_name)
        except ImportError:
            print(f"[HF Startup] Installing {pkg}...")
            try:
                cmd = [sys.executable, "-m", "pip", "install", pkg, "--quiet"]
                if pkg == "chatterbox-tts":
                    cmd = [sys.executable, "-m", "pip", "install", "chatterbox-tts", "--no-deps", "--quiet"]
                subprocess.check_call(cmd)
                print(f"[HF Startup] {pkg} installed successfully.")
            except Exception as e:
                print(f"[HF Startup Warning] {pkg} note: {e}")
    try:
        with open("/tmp/.chatterbox_installed", "w") as f:
            f.write("ok")
    except Exception:
        pass

import spaces
import gradio as gr
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 2.5 Auto-sync root files into backend/ in case files were uploaded to space root
import shutil
os.makedirs("backend", exist_ok=True)
for fname in ["tts_engine.py", "twilio_service.py", "rag_engine.py", "llm_engine.py", "main.py", "database.py", "models.py", "config.py"]:
    if os.path.exists(fname):
        dest = os.path.join("backend", fname)
        try:
            shutil.copy2(fname, dest)
            print(f"[HF Auto-Sync] Synced {fname} into backend/{fname}")
        except Exception as sync_err:
            print(f"[HF Auto-Sync Warning] Could not sync {fname}: {sync_err}")

from backend.database import init_db
from backend.config import UPLOADED_DOCS_DIR, TTS_OUTPUT_DIR
from backend.main import app as fastapi_app

# 3. Clear background pre-warming threads to prevent ZeroGPU shutdown
try:
    fastapi_app.router.on_startup.clear()
except Exception:
    pass

init_db()
os.makedirs(UPLOADED_DOCS_DIR, exist_ok=True)
os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)

# 4. ZeroGPU inference & pre-warming functions (scanned and detected by Hugging Face ZeroGPU runtime)
@spaces.GPU(duration=60)
def zero_gpu_synthesize(text: str = "Hello", ref_audio: str = None):
    try:
        from backend import tts_engine
        return tts_engine.synthesize(text, ref_audio)
    except Exception as exc:
        print(f"[ZeroGPU Synthesis Error]: {exc}")
        return ""

@spaces.GPU(duration=60)
def zero_gpu_prewarm():
    try:
        from backend import tts_engine
        res = tts_engine.prewarm_engine()
        return f"Cloned voice pre-warmed successfully: {res}"
    except Exception as exc:
        print(f"[ZeroGPU Prewarm Error]: {exc}")
        return f"Prewarm error: {exc}"

# 5. Gradio Interface (Mandatory for ZeroGPU detection)
with gr.Blocks(title="Vocalyx Backend (ZeroGPU)") as demo:
    gr.Markdown("## 🎙️ Vocalyx AI Telephony Backend (ZeroGPU Active)")
    gr.Markdown("FastAPI REST endpoints, Twilio Webhook, and NVIDIA A100 voice cloning are online.")
    with gr.Row():
        txt_in = gr.Textbox(label="Voice Test Input", value="Vocalyx AI Telephony is online and ready.")
        txt_out = gr.Textbox(label="Output Audio Path")
    with gr.Row():
        test_btn = gr.Button("Test Voice Clone on ZeroGPU", variant="primary")
        prewarm_btn = gr.Button("🔥 Pre-Warm Cloned Voice Engine", variant="secondary")
    test_btn.click(fn=zero_gpu_synthesize, inputs=[txt_in], outputs=[txt_out])
    prewarm_btn.click(fn=zero_gpu_prewarm, inputs=[], outputs=[txt_out])

# 6. Hook into Gradio's App.create_app so all FastAPI routes are attached to the running server
orig_create_app = gr.routes.App.create_app

def patched_create_app(*args, **kwargs):
    server_app = orig_create_app(*args, **kwargs)
    try:
        server_app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    except Exception:
        pass
    server_app.include_router(fastapi_app.router)
    server_app.mount("/tts_output", StaticFiles(directory=TTS_OUTPUT_DIR), name="tts_output")
    return server_app

gr.routes.App.create_app = patched_create_app

# 7. Launch using Gradio's native launcher (Mandatory for Hugging Face ZeroGPU SDK)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    try:
        demo.launch(server_name="0.0.0.0", server_port=port, ssr_mode=False, share=False)
    except TypeError:
        try:
            demo.launch(server_name="0.0.0.0", server_port=port, ssr=False, share=False)
        except TypeError:
            demo.launch(server_name="0.0.0.0", server_port=port, share=False)
