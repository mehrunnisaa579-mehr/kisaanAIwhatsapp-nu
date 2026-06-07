import wave
import math
import struct
import io
import sys
from fastapi.testclient import TestClient

sys.stdout.reconfigure(encoding='utf-8')
from main import app

client = TestClient(app)

def generate_mock_wav() -> bytes:
    """Generates a 1-second 440Hz sine wave WAV file in memory."""
    sample_rate = 8000
    duration = 1.0
    num_samples = int(sample_rate * duration)
    
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2) # 16-bit
        wav_file.setframerate(sample_rate)
        
        for i in range(num_samples):
            value = int(10000 * math.sin(2 * math.pi * 440 * i / sample_rate))
            data = struct.pack('<h', value)
            wav_file.writeframes(data)
            
    return wav_io.getvalue()

def run_tests():
    audio_bytes = generate_mock_wav()
    
    test_cases = [
        {
            "name": "1. Valid Audio File",
            "files": {
                "audio": ("voice_note.wav", audio_bytes, "audio/wav")
            },
            "data": {
                "latitude": "31.5204",
                "longitude": "74.3587",
                "language_hint": "ur"
            }
        },
        {
            "name": "2. Missing Audio File",
            "files": {
                "audio": ("voice_note.wav", b"", "audio/wav")
            },
            "data": {}
        },
        {
            "name": "3. Large Audio File (Simulated)",
            "files": {
                "audio": ("voice_note.wav", b"\x00" * (9 * 1024 * 1024), "audio/wav")  # 9 MB
            },
            "data": {}
        }
    ]

    for tc in test_cases:
        print("\n" + "="*50)
        print(f"RUNNING VOICE TEST: {tc['name']}")
        print("="*50)
        
        response = client.post("/voice-analyze", data=tc["data"], files=tc["files"])
        print(f"Status Code: {response.status_code}")
        res = response.json()
        
        print("Transcript:")
        print(res.get("transcript"))
        print("\nFarmer Response:")
        print(res.get("farmer_response"))
        print("\nTTS Summary:")
        print(res.get("tts_summary"))
        print("\nAudio URL:")
        print(res.get("audio_url"))
        print("\nVoice Status:")
        print(res.get("voice_status"))
        print("\nGemini Status:")
        print(res.get("gemini_status"))

if __name__ == "__main__":
    run_tests()
