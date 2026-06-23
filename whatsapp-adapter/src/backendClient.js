const axios = require('axios');

/**
 * Sends a text message query to the FarmAI FastAPI backend integration endpoint.
 * 
 * @param {object} params
 * @param {string} params.userId - Phone number (JID without domain)
 * @param {string} params.text - The text query from the farmer
 * @returns {Promise<object>} Structured response object indicating success or failure
 */
async function sendTextToBackend({ userId, text }) {
  const baseUrl = process.env.BACKEND_BASE_URL || 'https://kisaanaiwhatsapp-nu.onrender.com';
  const source = process.env.SOURCE_NAME || 'whatsapp_baileys';

  try {
    const response = await axios.post(`${baseUrl}/integration/process`, {
      user_id: userId,
      source: source,
      message_type: 'text',
      text: text
    }, {
      timeout: 60000 // 60 seconds timeout
    });

    return {
      success: true,
      data: response.data
    };
  } catch (error) {
    console.error('[WA] backend error:', error.message);
    return {
      success: false,
      error: error
    };
  }
}

module.exports = {
  sendTextToBackend
};
