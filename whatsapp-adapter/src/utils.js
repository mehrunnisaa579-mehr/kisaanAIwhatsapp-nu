/**
 * Utility functions for the FarmAI WhatsApp Adapter.
 */

/**
 * Extracts phone number/user ID from WhatsApp JID.
 * Example: 923001234567@s.whatsapp.net -> 923001234567
 * 
 * @param {string} jid - WhatsApp JID
 * @returns {string} User ID
 */
function jidToUserId(jid) {
  if (!jid) return '';
  return jid.split('@')[0];
}

/**
 * Extracts text content from a Baileys message object.
 * Checks for both standard conversation and extended text messages.
 * 
 * @param {object} message - Baileys message object
 * @returns {string|null} Text content or null if not text
 */
function extractTextMessage(message) {
  if (!message) return null;

  if (message.conversation) {
    return message.conversation;
  }

  if (message.extendedTextMessage && message.extendedTextMessage.text) {
    return message.extendedTextMessage.text;
  }

  return null;
}

/**
 * Creates a unique deduplication key for a message using remoteJid and message ID.
 * 
 * @param {string} remoteJid - The JID of the sender/chat
 * @param {string} id - The unique message ID
 * @returns {string} Unique message key
 */
function getMessageKey(remoteJid, id) {
  return `${remoteJid}:${id}`;
}

module.exports = {
  jidToUserId,
  extractTextMessage,
  getMessageKey
};

