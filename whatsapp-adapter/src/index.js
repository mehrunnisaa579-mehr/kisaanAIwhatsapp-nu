require('dotenv').config();
const { makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const { handleIncomingMessage } = require('./messageHandler');

/**
 * Initializes and connects the Baileys WhatsApp client, manages authorization state,
 * handles reconnection, and processes incoming message events.
 */
async function startWhatsAppAdapter() {
  const sessionPath = process.env.WHATSAPP_SESSION_PATH || './auth_info_baileys';
  
  // Set up multi-file auth state to save session data
  const { state, saveCreds } = await useMultiFileAuthState(sessionPath);

  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: false // We print it manually to log '[WA] QR received'
  });

  // Save session credentials whenever they update
  sock.ev.on('creds.update', saveCreds);

  // Monitor connection updates
  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('[WA] QR received');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      
      console.log(`[WA] Connection closed. Reconnecting: ${shouldReconnect}`, lastDisconnect?.error);
      
      if (shouldReconnect) {
        startWhatsAppAdapter();
      }
    } else if (connection === 'open') {
      console.log('[WA] connected');
    }
  });

  // Listen to incoming messages
  sock.ev.on('messages.upsert', async (m) => {
    if (m.type === 'notify') {
      for (const msg of m.messages) {
        await handleIncomingMessage(sock, msg);
      }
    }
  });
}

// Start the adapter
startWhatsAppAdapter().catch((err) => {
  console.error('[WA] Failed to start adapter:', err);
});
