# FarmAI WhatsApp Adapter (Baileys)

This directory contains a separate Node.js adapter skeleton for linking WhatsApp (via Baileys) with the FarmAI FastAPI backend.

## Supported Features

- **Phase 1: Text-Message Flow**: Routes text queries to the FarmAI `/integration/process` API endpoint.
- **Phase 2: Image-Only Flow**: Routes image uploads directly to the FarmAI `/integration/process-upload` API endpoint as `multipart/form-data`.

---

## Setup Instructions

1. **Navigate to the adapter directory**:
   ```bash
   cd whatsapp-adapter
   ```

2. **Configure environment variables**:
   Copy `.env.example` to a new `.env` file (do not check `.env` into git):
   ```bash
   cp .env.example .env
   ```
   Open the `.env` file and set your `BACKEND_BASE_URL` (for example, the deployed URL or `http://localhost:8000` if running backend locally).

3. **Install dependencies**:
   ```bash
   npm install
   ```

4. **Start the adapter**:
   ```bash
   npm start
   ```

5. **Authenticate**:
   Scan the generated QR code printed in the terminal using your WhatsApp application (Linked Devices).

---

## Manual Verification Tests

Once connected, verify the text-message and image flows with the following test scenarios:

### Test Case 1: Crop Disease Advisory (Text)
* **Action**: Send the message:
  ```text
  meri cotton ke patte peele ho rahe hain
  ```
* **Expected Response**: FarmAI crop disease diagnosis and advisory response.

### Test Case 2: Market Rates Advisory (Text)
* **Action**: Send the message:
  ```text
  gandum ka rate kya hai?
  ```
* **Expected Response**: Current market rate information for wheat (gandum).

### Test Case 3: Crop Disease Advisory (Image-Only)
* **Action**: Send a crop leaf image (optionally with or without a caption).
* **Expected Response**: FarmAI crop disease analysis and diagnosis text response.

### Test Case 4: Offline/Down Backend Fallback
* **Action**: Temporarily stop the backend or set an invalid `BACKEND_BASE_URL` in `.env`, restart the adapter, and send any text or image.
* **Expected Response**:
  - For text: `FarmAI backend abhi available nahi hai. Thori der baad dobara try karein.`
  - For image: `FarmAI backend abhi available nahi hai. Thori der baad dobara try karein.` (or timeout message if it aborts).

