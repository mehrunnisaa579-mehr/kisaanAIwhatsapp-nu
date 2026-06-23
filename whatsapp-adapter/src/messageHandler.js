const { downloadMediaMessage } = require('@whiskeysockets/baileys');
const { jidToUserId, extractTextMessage, getMessageKey, isAudioConfirmationText } = require('./utils');
const { 
  sendTextToBackend, 
  sendImageToBackend, 
  sendAudioToBackend, 
  resolveBackendUrl, 
  downloadBackendAudio 
} = require('./backendClient');

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
 * Decides and sends a backend audio reply based on authorization rules.
 * 
 * @param {object} params
 * @param {object} params.sock - Baileys socket instance
 * @param {string} params.remoteJid - Destination WhatsApp JID
 * @param {object} params.backendResponse - API response object from backend
 * @param {boolean} params.allowAudioReply - If audio reply is allowed for this message type/flow
 */
async function maybeSendBackendAudioReply({ sock, remoteJid, backendResponse, allowAudioReply }) {
  if (!allowAudioReply) {
    console.log('[WA] audio reply not allowed for this message type');
    return;
  }

  const audioUrl = backendResponse?.audio_url;
  if (!audioUrl) {
    console.log('[WA] no backend audio_url, text reply only');
    return;
  }

  console.log('[WA] backend audio_url found');

  if (backendResponse.whatsapp_ready === false) {
    console.log('[WA] backend audio not whatsapp-ready, skipping audio send');
    return;
  }

  const resolvedUrl = resolveBackendUrl(audioUrl);
  const isOgg = resolvedUrl && resolvedUrl.toLowerCase().endsWith('.ogg');
  const mimeType = isOgg ? 'audio/ogg; codecs=opus' : (resolvedUrl.toLowerCase().endsWith('.mp3') ? 'audio/mpeg' : (resolvedUrl.toLowerCase().endsWith('.wav') ? 'audio/wav' : 'audio/ogg; codecs=opus'));
  const ptt = isOgg;

  // Strategy 1: Try sending audio using direct URL payload
  try {
    const sentMsg = await sock.sendMessage(remoteJid, {
      audio: { url: resolvedUrl },
      mimetype: mimeType,
      ptt: ptt
    });

    console.log('[WA] audio reply sent', sentMsg?.key?.id || '');
    return;
  } catch (urlSendError) {
    console.log(`[WA] sending audio via direct URL failed, falling back to buffer download: ${urlSendError.message}`);
  }

  // Strategy 2: Fallback to downloaded Buffer
  try {
    const downloadResult = await downloadBackendAudio(resolvedUrl);

    if (!downloadResult.ok) {
      console.log(`[WA] audio reply failed ${downloadResult.error}`);
      return;
    }

    const bufferMimeType = isOgg ? 'audio/ogg; codecs=opus' : downloadResult.mimeType;

    const sentMsg = await sock.sendMessage(remoteJid, {
      audio: downloadResult.buffer,
      mimetype: bufferMimeType,
      ptt: ptt
    });

    console.log('[WA] audio reply sent', sentMsg?.key?.id || '');
  } catch (bufferSendError) {
    console.log(`[WA] audio reply failed ${bufferSendError.message}`);
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

    // Identify if the message contains valid text, an image, or a voice/audio note
    const isText = !!(extractTextMessage(msg.message));
    const isImage = !!(msg.message?.imageMessage);
    const isAudio = !!(msg.message?.audioMessage);

    // Ignore unsupported messages (like sticker, video, document, location for now)
    if (!isText && !isImage && !isAudio) {
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

    // Mark as processed BEFORE calling backend / downloading media to handle simultaneous duplicates
    processedMessageIds.set(messageKey, Date.now());

    // 5. Map JID to backend user_id
    const userId = jidToUserId(jid);

    if (isAudio) {
      console.log(`[WA] audio message received ${msg.key.id}`);

      try {
        // Download audio media buffer using Baileys helper
        const buffer = await downloadMediaMessage(
          msg,
          'buffer',
          {}
        );

        if (!buffer) {
          throw new Error('Downloaded buffer is empty or null');
        }

        const audioMsg = msg.message.audioMessage;
        const mimeType = audioMsg.mimetype || 'audio/ogg';

        // Call the backend with the audio buffer
        const result = await sendAudioToBackend({
          userId,
          audioBuffer: buffer,
          filename: 'voice.ogg',
          mimeType
        });

        if (!result.success) {
          let fallbackText = 'FarmAI backend abhi available nahi hai. Thori der baad dobara try karein.';
          if (result.error && (result.error.code === 'ECONNABORTED' || result.error.message.includes('timeout'))) {
            fallbackText = 'Voice note analyze karne mein zyada waqt lag raha hai. Thori der baad dobara try karein.';
          }
          await sock.sendMessage(jid, { text: fallbackText });
          return;
        }

        console.log('[WA] backend response received');

        const responseData = result.data;
        if (responseData && responseData.status === 'success' && responseData.farmer_response) {
          // Send text first
          await sock.sendMessage(jid, { text: responseData.farmer_response });
          // Send audio reply (allowed because incoming is audio)
          await maybeSendBackendAudioReply({
            sock,
            remoteJid: jid,
            backendResponse: responseData,
            allowAudioReply: true
          });
        } else {
          await sock.sendMessage(jid, { text: 'معذرت، آواز کا جواب تیار نہیں ہو سکا۔ دوبارہ کوشش کریں۔' });
        }

      } catch (mediaErr) {
        console.error('[WA] Error downloading or processing audio:', mediaErr.message);
        await sock.sendMessage(jid, { text: 'معذرت، آواز حاصل کرنے یا جواب بنانے میں مسئلہ پیش آیا۔ دوبارہ کوشش کریں۔' });
      }

    } else if (isImage) {
      console.log(`[WA] image message received ${msg.key.id}`);

      try {
        // Download image media buffer using Baileys helper
        const buffer = await downloadMediaMessage(
          msg,
          'buffer',
          {}
        );

        if (!buffer) {
          throw new Error('Downloaded buffer is empty or null');
        }

        const imageMsg = msg.message.imageMessage;
        const mimeType = imageMsg.mimetype || 'image/jpeg';
        const caption = imageMsg.caption || '';

        // Call the backend with the buffer
        const result = await sendImageToBackend({
          userId,
          imageBuffer: buffer,
          filename: `whatsapp_image_${msg.key.id}.jpg`,
          mimeType,
          caption
        });

        if (!result.success) {
          let fallbackText = 'FarmAI backend abhi available nahi hai. Thori der baad dobara try karein.';
          if (result.error && (result.error.code === 'ECONNABORTED' || result.error.message.includes('timeout'))) {
            fallbackText = 'Tasveer analyze karne mein zyada waqt lag raha hai. Thori der baad dobara try karein.';
          }
          await sock.sendMessage(jid, { text: fallbackText });
          return;
        }

        console.log('[WA] backend response received');

        const responseData = result.data;
        if (responseData && responseData.status === 'success' && responseData.farmer_response) {
          // Send text first
          await sock.sendMessage(jid, { text: responseData.farmer_response });
          // Call helper with false because image is not allowed to receive audio automatically
          await maybeSendBackendAudioReply({
            sock,
            remoteJid: jid,
            backendResponse: responseData,
            allowAudioReply: false
          });
        } else {
          await sock.sendMessage(jid, { text: 'معذرت، تصویر کا جواب تیار نہیں ہو سکا۔ دوبارہ کوشش کریں۔' });
        }

      } catch (mediaErr) {
        console.error('[WA] Error downloading or processing image:', mediaErr.message);
        await sock.sendMessage(jid, { text: 'معذرت، تصویر حاصل کرنے یا جواب بنانے میں مسئلہ پیش آیا۔ دوبارہ کوشش کریں۔' });
      }

    } else {
      // Text flow
      const text = extractTextMessage(msg.message);
      const isConfirmation = isAudioConfirmationText(text);

      console.log(`[WA] text message received ${msg.key.id}`);
      if (isConfirmation) {
        console.log('[WA] audio confirmation text detected');
      }

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
        // Send text first
        await sock.sendMessage(jid, { text: responseData.farmer_response });
        // Call helper with isConfirmation to send audio only if text was confirmation request
        await maybeSendBackendAudioReply({
          sock,
          remoteJid: jid,
          backendResponse: responseData,
          allowAudioReply: isConfirmation
        });
      } else {
        await sock.sendMessage(jid, { text: 'معذرت، ابھی جواب تیار نہیں ہو سکا۔ دوبارہ کوشش کریں۔' });
      }
    }

  } catch (err) {
    console.error('[WA] Error in handleIncomingMessage:', err);
  }
}

module.exports = {
  handleIncomingMessage
};




