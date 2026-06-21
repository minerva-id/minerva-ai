import os
import io
import asyncio
import base64
import aiohttp
from minerva.logger import get_logger

log = get_logger(__name__)

# Constants
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Default "Rachel" voice id from ElevenLabs, or use any standard

async def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Convert audio bytes to text using OpenAI Whisper API.
    Uses mock if OPENAI_API_KEY is not set.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log.info("STT: OPENAI_API_KEY not set. Using mock transcript.")
        await asyncio.sleep(1) # Simulate network latency
        return "System command received. Proceeding with analysis."
        
    try:
        data = aiohttp.FormData()
        # Whisper expects a file payload
        data.add_field('file',
                       audio_bytes,
                       filename='audio.webm',
                       content_type='audio/webm')
        data.add_field('model', 'whisper-1')

        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.openai.com/v1/audio/transcriptions", data=data, headers=headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("text", "")
                else:
                    err_text = await resp.text()
                    log.error(f"Whisper API error: {err_text}")
                    return "Error transcribing audio."
    except Exception as e:
        log.error(f"STT Exception: {str(e)}")
        return ""


async def synthesize_speech(text: str) -> str:
    """
    Convert text to speech using ElevenLabs API.
    Returns base64 encoded mp3 audio.
    Uses mock if ELEVENLABS_API_KEY is not set.
    """
    if not text.strip():
        return ""
        
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        log.info("TTS: ELEVENLABS_API_KEY not set. Using mock audio response.")
        await asyncio.sleep(0.5)
        # Return a tiny valid base64 MP3 or empty string. The browser will ignore empty or invalid gracefully if handled.
        # Actually returning a tiny silent MP3 base64 so frontend doesn't crash:
        silent_mp3_b64 = "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYwLjE2LjEwMAAAAAAAAAAAAAAA//OEAAAAAAAAAAAAAAAAAAAAAAAASW5mbwAAAA8AAAAEAAABIwBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBg//OEAAAAAAAAAAAAAAAAAAAAAAAAR0FNRQAAAA8AAABPAAAAMwD/OEAAAAAAAAAAAAAAAAAAAAAAAAR0FNRQAAAA8AAABPAAAAMwA="
        return silent_mp3_b64

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    audio_bytes = await resp.read()
                    return base64.b64encode(audio_bytes).decode('utf-8')
                else:
                    err_text = await resp.text()
                    log.error(f"ElevenLabs API error: {err_text}")
                    return ""
    except Exception as e:
        log.error(f"TTS Exception: {str(e)}")
        return ""
