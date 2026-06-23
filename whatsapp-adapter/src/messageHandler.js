const { jidToUserId, extractTextMessage, getMessageKey } = require('./utils');
const { sendTextToBackend } = require('./backendClient');

// In-memory cache of processed messages: messageKey -> timestamp
const processedMessageIds = new Map();
const DEDUPE_TTL_MS = 10 * 60 * 1000; // 10 minutes in milliseconds

/**
 * Cleans up message IDs older than 10 minutes from the cache to prevent memory leaks.
 */
function cleanExpiredMessageIds() {
  const now = Date.now();
  for (const [key, timestamp] of processedMessageIds.entries()) {
    if (now - timestamp > DEDUPE_TTL_MS) {
      processedMessageIds.delete(key);
    }
  }
}

/**
 * Handles incoming WhatsApp messages, performs validation, requests backend processing,
 * and replies to the user with the response or fallback messages.
 * 
 * @param {object} sock - Baileys socket instance
 * @param {object} msg - Incoming Baileys message object
 */
async function handleIncomingMessage(sock, msg) {
  try {
    const jid = msg.key.remoteJid;
    if (!jid) return;

    // 1. Ignore status broadcasts
    if (jid === 'status@broadcast') {
      return;
    }

    // 2. Ignore group messages
    if (jid.endsWith('@g.us')) {
      return;
    }

    // 3. Ignore messages from self
    if (msg.key.fromMe) {
      return;
    }

    // 4. Extract and validate text
    const text = extractTextMessage(msg.message);
    if (!text || !text.trim()) {
      // Ignore empty or media messages
      return;
    }

    // Deduplication check using message id + remote JID
    const messageKey = getMessageKey(jid, msg.key.id);

    // Periodically clean up expired cached IDs
    cleanExpiredMessageIds();

    if (processedMessageIds.has(messageKey)) {
      console.log(`[WA] duplicate message ignored ${msg.key.id}`);
      return;
    }

    // Mark as processed BEFORE calling backend to handle simultaneous duplicates
    processedMessageIds.set(messageKey, Date.now());

    console.log(`[WA] text message received ${msg.key.id}`);

    // 5. Map JID to backend user_id
    const userId = jidToUserId(jid);

    // 6. Send request to backend
    const result = await sendTextToBackend({ userId, text });

    if (!result.success) {
      // If request failed (e.g. timeout or down)
      let fallbackText = 'FarmAI backend abhi available nahi hai. Thori der baad dobara try karein.';
      
      if (result.error && (result.error.code === 'ECONNABORTED' || result.error.message.includes('timeout'))) {
        fallbackText = 'Jawab banne mein zyada waqt lag raha hai. Thori der baad dobara try karein.';
      }
      
      await sock.sendMessage(jid, { text: fallbackText });
      return;
    }

    console.log('[WA] backend response received');

    // 7. Send backend farmer_response back to the same WhatsApp chat
    const responseData = result.data;
    if (responseData && responseData.status === 'success' && responseData.farmer_response) {
      await sock.sendMessage(jid, { text: responseData.farmer_response });
    } else {
      await sock.sendMessage(jid, { text: 'معذرت، ابھی جواب تیار نہیں ہو سکا۔ دوبارہ کوشش کریں۔' });
    }

  } catch (err) {
    console.error('[WA] Error in handleIncomingMessage:', err);
  }
}

module.exports = {
  handleIncomingMessage
};

