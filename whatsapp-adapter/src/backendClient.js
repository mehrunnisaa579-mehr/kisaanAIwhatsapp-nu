const axios = require('axios');
const FormData = require('form-data');

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

/**
 * Sends an image file buffer and optional text caption to the FarmAI FastAPI backend.
 * 
 * @param {object} params
 * @param {string} params.userId - Phone number (JID without domain)
 * @param {Buffer} params.imageBuffer - The image file buffer downloaded from WhatsApp
 * @param {string} [params.filename] - Filename for the image file upload
 * @param {string} [params.mimeType] - MIME type of the image file
 * @param {string} [params.caption] - Optional caption text from the user
 * @returns {Promise<object>} Structured response object indicating success or failure
 */
async function sendImageToBackend({ userId, imageBuffer, filename, mimeType, caption }) {
  const baseUrl = process.env.BACKEND_BASE_URL || 'https://kisaanaiwhatsapp-nu.onrender.com';
  const source = process.env.SOURCE_NAME || 'whatsapp_baileys';

  const form = new FormData();
  form.append('user_id', userId);
  form.append('source', source);
  form.append('message_type', 'image');
  form.append('crop', '');

  // Append image buffer with filename and content type metadata
  form.append('image', imageBuffer, {
    filename: filename || 'image.jpg',
    contentType: mimeType || 'image/jpeg'
  });

  if (caption && caption.trim()) {
    form.append('text', caption.trim());
  }

  try {
    const response = await axios.post(`${baseUrl}/integration/process-upload`, form, {
      headers: form.getHeaders(),
      timeout: 90000 // 90 seconds timeout for image analysis
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
  sendTextToBackend,
  sendImageToBackend
};

