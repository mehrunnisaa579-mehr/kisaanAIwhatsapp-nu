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

/**
 * Sends an audio file buffer (voice note) to the FarmAI FastAPI backend.
 * 
 * @param {object} params
 * @param {string} params.userId - Phone number (JID without domain)
 * @param {Buffer} params.audioBuffer - The audio file buffer downloaded from WhatsApp
 * @param {string} [params.filename] - Filename for the audio upload (defaults to voice.ogg)
 * @param {string} [params.mimeType] - MIME type of the audio file (defaults to audio/ogg)
 * @returns {Promise<object>} Structured response object indicating success or failure
 */
async function sendAudioToBackend({ userId, audioBuffer, filename, mimeType }) {
  const baseUrl = process.env.BACKEND_BASE_URL || 'https://kisaanaiwhatsapp-nu.onrender.com';
  const source = process.env.SOURCE_NAME || 'whatsapp_baileys';

  const form = new FormData();
  form.append('user_id', userId);
  form.append('source', source);
  form.append('message_type', 'audio');
  form.append('crop', '');

  // Append audio buffer using the field name 'audio'
  form.append('audio', audioBuffer, {
    filename: filename || 'voice.ogg',
    contentType: mimeType || 'audio/ogg'
  });

  try {
    const response = await axios.post(`${baseUrl}/integration/process-upload`, form, {
      headers: form.getHeaders(),
      timeout: 120000 // 120 seconds timeout for STT + AI response
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
 * Resolves a potentially relative URL or file path against the BACKEND_BASE_URL.
 * 
 * @param {string} pathOrUrl - File path or URL
 * @returns {string|null} Resolved URL or null
 */
function resolveBackendUrl(pathOrUrl) {
  if (!pathOrUrl) return null;
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  const baseUrl = process.env.BACKEND_BASE_URL || 'https://kisaanaiwhatsapp-nu.onrender.com';
  return `${baseUrl.replace(/\/$/, '')}/${pathOrUrl.replace(/^\//, '')}`;
}

/**
 * Downloads a binary audio payload from a backend URL.
 * 
 * @param {string} audioUrl - URL of the audio file to download
 * @returns {Promise<object>} Result containing ok status, buffer, and mimeType or error
 */
async function downloadBackendAudio(audioUrl) {
  try {
    const response = await axios.get(audioUrl, {
      responseType: 'arraybuffer',
      timeout: 60000 // 60 seconds
    });

    let mimeType = 'audio/ogg; codecs=opus'; // Default
    const contentType = response.headers['content-type'];
    
    if (contentType) {
      mimeType = contentType;
    } else {
      // Infer mimeType from file extension if headers are missing
      if (audioUrl.endsWith('.ogg')) {
        mimeType = 'audio/ogg; codecs=opus';
      } else if (audioUrl.endsWith('.mp3')) {
        mimeType = 'audio/mpeg';
      } else if (audioUrl.endsWith('.wav')) {
        mimeType = 'audio/wav';
      }
    }

    return {
      ok: true,
      buffer: Buffer.from(response.data),
      mimeType
    };
  } catch (error) {
    return {
      ok: false,
      error: error.message
    };
  }
}

/**
 * Sends a location pin to the FarmAI FastAPI backend.
 * 
 * @param {object} params
 * @param {string} params.userId - Phone number (JID without domain)
 * @param {number} params.latitude - Latitude degrees
 * @param {number} params.longitude - Longitude degrees
 * @param {string} [params.name] - Optional name of the location
 * @param {string} [params.address] - Optional address of the location
 * @returns {Promise<object>} Structured response object indicating success or failure
 */
async function sendLocationToBackend({ userId, latitude, longitude, name, address }) {
  const baseUrl = process.env.BACKEND_BASE_URL || 'https://kisaanaiwhatsapp-nu.onrender.com';
  const source = process.env.SOURCE_NAME || 'whatsapp_baileys';

  try {
    const response = await axios.post(`${baseUrl}/integration/process`, {
      user_id: userId,
      source: source,
      message_type: 'location',
      text: 'Location shared',
      latitude: latitude,
      longitude: longitude,
      location_name: name || '',
      location_address: address || ''
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
  sendTextToBackend,
  sendImageToBackend,
  sendAudioToBackend,
  sendLocationToBackend,
  resolveBackendUrl,
  downloadBackendAudio
};



