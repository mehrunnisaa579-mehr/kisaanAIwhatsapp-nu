import sys
import base64
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# Programmatically generate test images using Pillow
from PIL import Image, ImageDraw
import io

# 1. Relevant image (green background with yellow box and red line, non-solid)
img_relevant = Image.new("RGB", (100, 100), color="green")
draw = ImageDraw.Draw(img_relevant)
draw.rectangle([30, 30, 70, 70], fill="yellow")
draw.line([0, 0, 100, 100], fill="red", width=3)
relevant_io = io.BytesIO()
img_relevant.save(relevant_io, format="JPEG")
relevant_jpeg_bytes = relevant_io.getvalue()

# 2. Solid/irrelevant image (solid black, 100x100)
img_solid = Image.new("RGB", (100, 100), color="black")
solid_io = io.BytesIO()
img_solid.save(solid_io, format="JPEG")
solid_jpeg_bytes = solid_io.getvalue()

test_cases = [
    # 1. Urdu agriculture
    {
        "name": "1. Urdu Agriculture",
        "payload": {
            "text": "میری کپاس کے پتوں پر پیلے نشان ہیں",
            "crop": "Cotton"
        }
    },
    # 2. Roman Urdu agriculture
    {
        "name": "2. Roman Urdu Agriculture",
        "payload": {
            "text": "Meri kapas ke patton par peelay nishan hain",
            "crop": "Cotton"
        }
    },
    # 3. English agriculture
    {
        "name": "3. English Agriculture",
        "payload": {
            "text": "My cotton leaves have yellow spots",
            "crop": "Cotton"
        }
    },
    # 4. Urdu irrelevant
    {
        "name": "4. Urdu Irrelevant",
        "payload": {
            "text": "مجھے فلم کی کہانی بتاؤ"
        }
    },
    # 5. Roman Urdu irrelevant
    {
        "name": "5. Roman Urdu Irrelevant",
        "payload": {
            "text": "Mujhe movie ki story batao"
        }
    },
    # 6. English irrelevant
    {
        "name": "6. English Irrelevant",
        "payload": {
            "text": "Tell me a joke"
        }
    },
    # 7. Invalid/Corrupt Image
    {
        "name": "7. Invalid/Corrupt Image",
        "payload": {
            "text": "",
        },
        "files": {
            "image": ("test_image.jpg", b"mock_data_bytes", "image/jpeg")
        }
    },
    # 8. Text + Image (relevant)
    {
        "name": "8. Text + Image (relevant)",
        "payload": {
            "text": "My cotton crop is showing this issue",
            "crop": "Cotton"
        },
        "files": {
            "image": ("valid_image.jpg", relevant_jpeg_bytes, "image/jpeg")
        }
    },
    # 9. Image Only (irrelevant - solid color)
    {
        "name": "9. Image Only (irrelevant - solid color)",
        "payload": {
            "text": "",
        },
        "files": {
            "image": ("irrelevant_image.jpg", solid_jpeg_bytes, "image/jpeg")
        }
    },
    # 10. Both missing (validation error)
    {
        "name": "10. Both missing (validation error)",
        "payload": {
            "text": "",
        }
    }
]

for tc in test_cases:
    print(f"\n==================================================")
    print(f"RUNNING TEST: {tc['name']}")
    print(f"Payload: {tc['payload']}")
    print(f"==================================================")
    
    if "files" in tc:
        r = client.post("/analyze", data=tc["payload"], files=tc["files"])
    else:
        r = client.post("/analyze", data=tc["payload"])
        
    print(f"Status Code: {r.status_code}")
    res = r.json()
    print("Farmer Response:")
    print(res.get("farmer_response"))
    print("\nTTS Summary:")
    print(res.get("tts_summary"))
    print("\nGemini Status:")
    print(res.get("gemini_status"))
