// FarmAI Backend API Service
//
// If testing on Android phone through Expo Go,
// replace 127.0.0.1 with your laptop's local IP address
// or use an ngrok URL.
// Example: const BASE_URL = 'http://192.168.1.100:8000';

const BASE_URL = 'http://192.168.1.19:8000';
const API_URL = `${BASE_URL}/analyze`;
const TIMEOUT_MS = 60000; // 60 seconds

export async function analyzeCrop({ text, crop, latitude, longitude, image }) {
  console.log("Sending request to backend...", API_URL);

  const formData = new FormData();

  // Append text fields safely — never append null/undefined
  if (text) {
    formData.append('text', text);
  }
  formData.append('crop', crop || '');

  if (latitude !== null && latitude !== undefined) {
    formData.append('latitude', String(latitude));
  }
  if (longitude !== null && longitude !== undefined) {
    formData.append('longitude', String(longitude));
  }

  // Append image safely — handle both URI string and object with .uri
  if (image) {
    const imageUri = typeof image === 'string' ? image : image.uri;
    if (imageUri) {
      const filename = imageUri.split('/').pop();
      const ext = filename.split('.').pop().toLowerCase();
      const mimeType = ext === 'png' ? 'image/png' : 'image/jpeg';
      formData.append('image', {
        uri: imageUri,
        name: filename,
        type: mimeType,
      });
    }
  }

  // AbortController for 20-second timeout protection
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
  }, TIMEOUT_MS);

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      body: formData,
      headers: {
        Accept: 'application/json',
      },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const data = await response.json();
    console.log("Response received");

    if (!response.ok) {
      throw new Error(data?.detail || `Server error (${response.status})`);
    }

    return data;
  } catch (error) {
    clearTimeout(timeoutId);

    if (error.name === 'AbortError') {
      console.log("Request timed out after", TIMEOUT_MS, "ms");
      throw new Error('جواب آنے میں زیادہ وقت لگ رہا ہے، دوبارہ کوشش کریں۔');
    }

    console.log("Frontend API error:", error);
    throw error;
  }
}

export async function fetchLiveWeather(latitude, longitude) {
  const url = `${BASE_URL}/weather?latitude=${latitude}&longitude=${longitude}`;
  console.log("Fetching live weather from:", url);
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Weather fetch failed (${response.status})`);
    }
    const data = await response.json();
    console.log("Live weather data received:", data);
    return data;
  } catch (error) {
    console.log("Error in fetchLiveWeather:", error);
    throw error;
  }
}

export async function generateTTS(text, languageHint = null) {
  const url = `${BASE_URL}/tts`;
  console.log("Requesting TTS from:", url);
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        text,
        language_hint: languageHint,
      }),
    });

    const data = await response.json();
    if (!response.ok || data.status === 'error') {
      throw new Error(data.message || `TTS failed (${response.status})`);
    }
    return data;
  } catch (error) {
    console.log("Error in generateTTS:", error);
    throw error;
  }
}

export async function voiceAnalyze({ audioUri, latitude, longitude, languageHint = null }) {
  const url = `${BASE_URL}/voice-analyze`;
  console.log("Sending voice analysis request to:", url);

  const formData = new FormData();
  if (audioUri) {
    const filename = audioUri.split('/').pop() || 'voice_note.m4a';
    let ext = filename.split('.').pop().toLowerCase();
    if (ext === 'm4p' || ext === 'm4a' || ext === 'aac' || ext === 'mp4') {
      ext = 'm4a';
    } else if (ext !== 'wav' && ext !== 'mp3' && ext !== 'webm') {
      ext = 'm4a';
    }
    const mimeType = `audio/${ext === 'm4a' ? 'x-m4a' : ext}`;

    formData.append("audio", {
      uri: audioUri,
      name: `voice_note.${ext}`,
      type: mimeType,
    });
  }

  if (latitude !== null && latitude !== undefined) {
    formData.append('latitude', String(latitude));
  }
  if (longitude !== null && longitude !== undefined) {
    formData.append('longitude', String(longitude));
  }
  if (languageHint) {
    formData.append('language_hint', languageHint);
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
  }, TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      headers: {
        Accept: 'application/json',
      },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    const data = await response.json();
    console.log("Voice Response received", data?.status);

    if (!response.ok) {
      throw new Error(data?.detail || `Server error (${response.status})`);
    }
    return data;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      console.log("Voice request timed out after", TIMEOUT_MS, "ms");
      throw new Error('جواب آنے میں زیادہ وقت لگ رہا ہے، دوبارہ کوشش کریں۔');
    }
    console.log("Frontend API voice error:", error);
    throw error;
  }
}
