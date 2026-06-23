# FarmAI WhatsApp Adapter (Baileys)

This directory contains a separate Node.js adapter skeleton for linking WhatsApp (via Baileys) with the FarmAI FastAPI backend.

## Phase 1: Text-Message Flow

This adapter implements only text-message processing, routing queries from WhatsApp users directly to the FarmAI core integration API, and sending responses back as text.

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

Once connected, verify the text-message flow with the following test scenarios:

### Test Case 1: Crop Disease Advisory
* **Action**: Send the message:
  ```text
  meri cotton ke patte peele ho rahe hain
  ```
* **Expected Response**: FarmAI crop disease diagnosis and advisory response.

### Test Case 2: Market Rates Advisory
* **Action**: Send the message:
  ```text
  gandum ka rate kya hai?
  ```
* **Expected Response**: Current market rate information for wheat (gandum).

### Test Case 3: Offline/Down Backend Fallback
* **Action**: Temporarily stop the backend or set an invalid `BACKEND_BASE_URL` in `.env`, restart the adapter, and send any text message.
* **Expected Response**:
  ```text
  FarmAI backend abhi available nahi hai. Thori der baad dobara try karein.
  ```
