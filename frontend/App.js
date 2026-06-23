import React, { useState, useRef, useEffect } from 'react';
import {
  SafeAreaView,
  ScrollView,
  View,
  Text,
  Image,
  StyleSheet,
  StatusBar,
  Platform,
  TouchableOpacity,
  KeyboardAvoidingView,
  Alert,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Location from 'expo-location';
import { Audio } from 'expo-av';

import MultimodalInput from './components/MultimodalInput';
import WeatherCard from './components/WeatherCard';
import LoadingSpinner from './components/LoadingSpinner';
import { analyzeCrop, fetchLiveWeather, generateTTS, voiceAnalyze } from './services/api';

const CHAT_STORAGE_KEY = 'farmai_chat_messages';

const containsUrdu = (text) => {
  if (!text) return false;
  const urduCount = (text.match(/[\u0600-\u06FF]/g) || []).length;
  const latinCount = (text.match(/[a-zA-Z]/g) || []).length;
  return urduCount > latinCount;
};

const HEADINGS_MAP = {
  ur: [
    ["ممکنہ مسئلہ", "ممکنہ مسئلہ:"],
    ["خطرے کی سطح", "خطرے کی سطح:"],
    ["تجویز کردہ عمل", "تجویز کردہ عمل:"],
    ["موسم کا خیال", "موسم کا خیال:"],
    ["اگلا قدم", "اگلا قدم:"]
  ],
  roman_urdu: [
    ["mumkin masla", "Mumkin Masla:"],
    ["khatray ki satah", "Khatray ki Satah:"],
    ["tajweez kardah amal", "Tajweez Kardah Amal:"],
    ["mosam ka khayal", "Mosam ka Khayal:"],
    ["agla qadam", "Agla Qadam:"]
  ],
  english: [
    ["possible issue", "Possible Issue:"],
    ["risk level", "Risk Level:"],
    ["recommended action", "Recommended Action:"],
    ["weather note", "Weather Note:"],
    ["next step", "Next Step:"]
  ]
};

function cleanAndShortenSection(text, maxSentences) {
  if (!text) return "";
  
  // Clean bullets, numbering, asterisks, brackets, parentheses, percent signs
  let cleaned = text.replace(/^\s*[-*+•]\s*/gm, '');
  cleaned = cleaned.replace(/^\s*\d+[\s\.)\-:]*/gm, '');
  cleaned = cleaned.replace(/\*\*/g, '').replace(/\*/g, '').replace(/__/g, '').replace(/_/g, '');
  cleaned = cleaned.replace(/[\(\)\[\]\{\}%]/g, ' ');
  cleaned = cleaned.replace(/⚠/g, '').replace(/-/g, '—');
  
  // Split into sentences (Urdu full stop is \u06D4, English is .)
  const sentences = cleaned.split(/[۔\.\n!\?]/);
  const cleanSentences = [];
  
  for (let s of sentences) {
    s = s.trim();
    if (s && s.length > 2) {
      cleanSentences.push(s);
    }
  }
  
  const selected = cleanSentences.slice(0, maxSentences);
  const isUrdu = /[\u0600-\u06FF]/.test(text);
  const separator = isUrdu ? "۔ " : ". ";
  const endChar = isUrdu ? "۔" : ".";
  
  let joined = selected.join(separator);
  if (joined && !joined.endsWith(endChar)) {
    joined += endChar;
  }
  return joined;
}

function getShortenedSummary(text) {
  if (!text) return "";
  
  let lang = "ur";
  const textLower = text.toLowerCase();
  
  const hasEnglishHeadings = textLower.includes("possible issue") || textLower.includes("risk level");
  const hasRomanHeadings = textLower.includes("mumkin masla") || textLower.includes("khatray ki satah");
  
  if (hasEnglishHeadings) {
    lang = "english";
  } else if (hasRomanHeadings) {
    lang = "roman_urdu";
  } else {
    const urduCount = (text.match(/[\u0600-\u06FF]/g) || []).length;
    const latinCount = (text.match(/[a-zA-Z]/g) || []).length;
    if (latinCount > urduCount) {
      const romanKeywords = ["yeh", "sirf", "fasal", "podon", "masla", "tasveer", "bhejein", "hai", "ke", "liye", "zaraati"];
      const hasRomanWords = romanKeywords.some(kw => textLower.includes(kw));
      lang = hasRomanWords ? "roman_urdu" : "english";
    } else {
      lang = "ur";
    }
  }

  const headingsList = HEADINGS_MAP[lang];
  const found = [];
  
  for (const [key, displayName] of headingsList) {
    const idx = textLower.indexOf(key.toLowerCase());
    if (idx !== -1) {
      found.push({ idx, key, displayName });
    }
  }
  
  if (found.length === 0) {
    return cleanAndShortenSection(text, 3);
  }
  
  found.sort((a, b) => a.idx - b.idx);
  
  const sections = {};
  for (let i = 0; i < found.length; i++) {
    const { idx, key, displayName } = found[i];
    let startIdx = idx + key.length;
    while (startIdx < text.length && (text[startIdx] === ':' || text[startIdx] === ' ' || text[startIdx] === '\t' || text[startIdx] === '\n')) {
      startIdx++;
    }
    const endIdx = (i + 1 < found.length) ? found[i+1].idx : text.length;
    sections[key] = text.substring(startIdx, endIdx).trim();
  }
  
  const summaryParts = [];
  let expectedHeadings = [];
  if (lang === "ur") {
    expectedHeadings = [
      ["ممکنہ مسئلہ", "ممکنہ مسئلہ:", 1],
      ["خطرے کی سطح", "خطرے کی سطح:", 1],
      ["تجویز کردہ عمل", "تجویز کردہ عمل:", 3],
      ["موسم کا خیال", "موسم کا خیال:", 1],
      ["اگلا قدم", "اگلا قدم:", 1]
    ];
  } else if (lang === "roman_urdu") {
    expectedHeadings = [
      ["mumkin masla", "Mumkin Masla:", 1],
      ["khatray ki satah", "Khatray ki Satah:", 1],
      ["tajweez kardah amal", "Tajweez Kardah Amal:", 3],
      ["mosam ka khayal", "Mosam ka Khayal:", 1],
      ["agla qadam", "Agla Qadam:", 1]
    ];
  } else {
    expectedHeadings = [
      ["possible issue", "Possible Issue:", 1],
      ["risk level", "Risk Level:", 1],
      ["recommended action", "Recommended Action:", 3],
      ["weather note", "Weather Note:", 1],
      ["next step", "Next Step:", 1]
    ];
  }
  
  for (const [key, displayName, maxSents] of expectedHeadings) {
    let content = "";
    for (const k of Object.keys(sections)) {
      if (k.toLowerCase() === key.toLowerCase()) {
        content = sections[k];
        break;
      }
    }
    
    if (!content) {
      for (const k of Object.keys(sections)) {
        if (key.toLowerCase().includes(k.toLowerCase()) || k.toLowerCase().includes(key.toLowerCase())) {
          content = sections[k];
          break;
        }
      }
    }
    
    if (content) {
      const shortContent = cleanAndShortenSection(content, maxSents);
      if (shortContent) {
        summaryParts.push(`${displayName} ${shortContent}`);
      }
    }
  }
  
  if (summaryParts.length === 0) {
    return cleanAndShortenSection(text, 5);
  }
  
  return summaryParts.join("\n");
}

function MessageImage({ uri, isImageOnly }) {
  const [error, setError] = useState(false);

  if (error) {
    return (
      <View style={styles.imageErrorContainer}>
        <Text style={styles.imageErrorText}>تصویر لوڈ نہیں ہو سکی</Text>
      </View>
    );
  }

  return (
    <Image
      source={{ uri }}
      style={[
        styles.userBubbleImage,
        isImageOnly && { marginBottom: 0 }
      ]}
      onError={() => setError(true)}
    />
  );
}

export default function App() {
  const [currentScreen, setCurrentScreen] = useState('Home');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const scrollViewRef = useRef(null);

  const [ttsStatus, setTtsStatus] = useState({});
  const soundRef = useRef(null);
  const [loadingMessage, setLoadingMessage] = useState(null);

  // Unmount cleanup for audio
  useEffect(() => {
    return () => {
      if (soundRef.current) {
        soundRef.current.unloadAsync().catch(() => {});
      }
    };
  }, []);

  const handlePlayTTS = async (msgId, text, languageHint, audioUrl = null) => {
    if (ttsStatus[msgId] === 'loading') return;

    try {
      if (soundRef.current) {
        console.log("Unloading previous sound...");
        await soundRef.current.stopAsync().catch(() => {});
        await soundRef.current.unloadAsync().catch(() => {});
        soundRef.current = null;
      }
    } catch (e) {
      console.log("Error unloading sound:", e);
    }

    if (ttsStatus[msgId] === 'playing') {
      setTtsStatus(prev => ({ ...prev, [msgId]: null }));
      return;
    }

    setTtsStatus(prev => {
      const updated = {};
      Object.keys(prev).forEach(key => {
        if (prev[key] === 'playing') {
          updated[key] = null;
        } else {
          updated[key] = prev[key];
        }
      });
      updated[msgId] = 'loading';
      return updated;
    });

    try {
      let finalAudioUrl = audioUrl;
      if (!finalAudioUrl) {
        console.log("Calling generateTTS for text:", text, "hint:", languageHint);
        const res = await generateTTS(text, languageHint);
        console.log("TTS URL received:", res.audio_url);
        finalAudioUrl = res.audio_url;
      } else {
        console.log("Reusing pre-generated audio URL:", finalAudioUrl);
      }

      const { sound } = await Audio.Sound.createAsync(
        { uri: finalAudioUrl },
        { shouldPlay: true }
      );

      soundRef.current = sound;
      setTtsStatus(prev => ({ ...prev, [msgId]: 'playing' }));

      sound.setOnPlaybackStatusUpdate((status) => {
        if (status.didJustFinish) {
          setTtsStatus(prev => ({ ...prev, [msgId]: null }));
          sound.unloadAsync().catch(() => {});
          if (soundRef.current === sound) {
            soundRef.current = null;
          }
        }
      });

    } catch (err) {
      console.log("TTS play failed:", err);
      setTtsStatus(prev => ({ ...prev, [msgId]: 'error' }));
    }
  };

  // Location and live weather state
  const [userCoords, setUserCoords] = useState(null);
  const [currentLocationName, setCurrentLocationName] = useState('مقام لوڈ ہو رہا ہے...');
  const [currentWeatherData, setCurrentWeatherData] = useState(null);

  // ── Fetch user location and live weather on mount ──
  useEffect(() => {
    async function getUserLocationAndWeather() {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status !== 'granted') {
          setCurrentLocationName('مقام کی اجازت نہیں دی گئی');
          return;
        }

        const location = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });

        if (location && location.coords) {
          const { latitude, longitude } = location.coords;
          setUserCoords({ latitude, longitude });

          // 1. Reverse Geocode for City/Country
          try {
            const geocode = await Location.reverseGeocodeAsync({
              latitude,
              longitude,
            });
            if (geocode && geocode.length > 0) {
              const place = geocode[0];
              const city = place.city || place.district || place.subregion || place.region || '';
              const country = place.country || '';
              if (city && country) {
                setCurrentLocationName(`${city}، ${country}`);
              } else if (city || country) {
                setCurrentLocationName(city || country);
              } else {
                setCurrentLocationName('منتقل مقام');
              }
            } else {
              setCurrentLocationName('منتقل مقام');
            }
          } catch (geoErr) {
            console.log("Geocoding error:", geoErr);
            setCurrentLocationName('منتقل مقام');
          }

          // 2. Fetch live weather from backend weather service
          try {
            const weather = await fetchLiveWeather(latitude, longitude);
            setCurrentWeatherData(weather);
          } catch (weatherErr) {
            console.log("Weather fetch error:", weatherErr);
          }
        } else {
          setCurrentLocationName('مقام دستیاب نہیں');
        }
      } catch (err) {
        console.log("Location/Weather initialization error:", err);
        setCurrentLocationName('مقام دستیاب نہیں');
      }
    }

    getUserLocationAndWeather();
  }, []);

  // ── Load chat from AsyncStorage on mount ──
  useEffect(() => {
    const loadChat = async () => {
      try {
        const saved = await AsyncStorage.getItem(CHAT_STORAGE_KEY);
        if (saved) {
          const parsed = JSON.parse(saved);
          if (Array.isArray(parsed)) {
            setChatMessages(parsed);
          }
        }
      } catch (e) {
        // Silently fail — chat starts empty
      }
    };
    loadChat();
  }, []);

  // ── Persist chat to AsyncStorage whenever messages change ──
  useEffect(() => {
    const saveChat = async () => {
      try {
        await AsyncStorage.setItem(
          CHAT_STORAGE_KEY,
          JSON.stringify(chatMessages)
        );
      } catch (e) {
        // Silently fail
      }
    };
    if (chatMessages.length > 0) {
      saveChat();
    }
  }, [chatMessages]);

  // ── Clear chat with confirmation ──
  const clearChat = () => {
    Alert.alert(
      'چیٹ صاف کریں',
      'کیا آپ واقعی پوری چیٹ صاف کرنا چاہتے ہیں؟',
      [
        { text: 'نہیں', style: 'cancel' },
        {
          text: 'ہاں',
          style: 'destructive',
          onPress: async () => {
            setChatMessages([]);
            setResult(null);
            setError(null);
            setTtsStatus({});
            try {
              if (soundRef.current) {
                await soundRef.current.stopAsync().catch(() => {});
                await soundRef.current.unloadAsync().catch(() => {});
                soundRef.current = null;
              }
            } catch (soundErr) {
              console.log("Error stopping sound on clear chat:", soundErr);
            }
            try {
              await AsyncStorage.removeItem(CHAT_STORAGE_KEY);
            } catch (e) {
              // Silently fail
            }
          },
        },
      ]
    );
  };

  const handleSubmit = async (inputData) => {
    // Validate input before starting loading
    if (!inputData.text?.trim() && !inputData.image && !inputData.voiceUri) {
      Alert.alert('ان پٹ ضروری ہے', 'براہ کرم اپنا مسئلہ لکھیں، تصویر، یا وائس نوٹ بھیجیں۔');
      return;
    }

    const isVoice = !!inputData.voiceUri;

    const userMsg = {
      id: Date.now().toString(),
      type: 'user',
      text: isVoice ? 'آواز ریکارڈنگ...' : (inputData.text || 'تصویر بھیجی گئی'),
      image: inputData.image,
      isImageOnly: !isVoice && !inputData.text?.trim(),
      isVoice: isVoice,
    };
    setChatMessages((prev) => [...prev, userMsg]);
    console.log("User message appended");

    setLoading(true);
    setLoadingMessage(isVoice ? "آواز سمجھ رہے ہیں..." : "کسان AI آپ کی فصل کا مسئلہ جانچ رہا ہے...");
    setError(null);
    setResult(null);

    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);

    try {
      console.log("Sending request to backend...");
      const payload = {
        ...inputData,
        latitude: userCoords?.latitude ?? inputData.latitude,
        longitude: userCoords?.longitude ?? inputData.longitude,
      };

      let result;
      if (isVoice) {
        result = await voiceAnalyze({
          audioUri: inputData.voiceUri,
          latitude: payload.latitude,
          longitude: payload.longitude,
        });

        // Update the user's message text with the actual transcribed text!
        if (result?.transcript) {
          setChatMessages((prev) =>
            prev.map((m) =>
              m.id === userMsg.id ? { ...m, text: result.transcript } : m
            )
          );
        } else {
          setChatMessages((prev) =>
            prev.map((m) =>
              m.id === userMsg.id ? { ...m, text: 'آواز موصول ہوئی' } : m
            )
          );
        }
      } else {
        result = await analyzeCrop(payload);
      }

      console.log("Backend response:", result);
      setResult(result);

      // Use farmer_response as primary, with fallbacks
      const replyText =
        result?.farmer_response ||
        result?.response ||
        result?.message ||
        'جواب موصول ہو گیا ہے۔';

      const aiMsg = {
        id: (Date.now() + 1).toString(),
        type: 'ai',
        text: replyText,
        ttsSummary: result?.tts_summary || null,
        audioUrl: result?.audio_url || null,
        data: result,
        createdAt: new Date().toISOString(),
      };
      setChatMessages((prev) => [...prev, aiMsg]);
      console.log("Appending AI message...");

      setTimeout(() => {
        scrollViewRef.current?.scrollToEnd({ animated: true });
      }, 200);

      // Auto-play the returned audio if voice input and audio url is available
      if (isVoice && result?.audio_url) {
        console.log("Auto-playing voice response...", result.audio_url);
        setTimeout(async () => {
          try {
            if (soundRef.current) {
              await soundRef.current.stopAsync().catch(() => {});
              await soundRef.current.unloadAsync().catch(() => {});
              soundRef.current = null;
            }

            const { sound } = await Audio.Sound.createAsync(
              { uri: result.audio_url },
              { shouldPlay: true }
            );

            soundRef.current = sound;
            setTtsStatus(prev => ({ ...prev, [aiMsg.id]: 'playing' }));

            sound.setOnPlaybackStatusUpdate((status) => {
              if (status.didJustFinish) {
                setTtsStatus(prev => ({ ...prev, [aiMsg.id]: null }));
                sound.unloadAsync().catch(() => {});
                if (soundRef.current === sound) {
                  soundRef.current = null;
                }
              }
            });
          } catch (playbackErr) {
            console.log("Auto-play failed:", playbackErr);
          }
        }, 500);
      }
    } catch (err) {
      console.log("Frontend API error:", err);
      const errorText = err.message || 'جواب حاصل نہیں ہو سکا، دوبارہ کوشش کریں۔';
      setError(errorText);
      const errMsg = {
        id: (Date.now() + 1).toString(),
        type: 'error',
        text: errorText,
      };
      setChatMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
      setLoadingMessage(null);
      console.log("Loading stopped");
    }
  };

  // ─── HOME SCREEN ───
  if (currentScreen === 'Home') {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="dark-content" backgroundColor="#f2f0ec" />
        <View style={styles.homeContainer}>
          <View style={styles.homeHeader}>
            <Text style={styles.homeTitle}>🌾 کسان AI</Text>
            <Text style={styles.homeSubtitle}>آپ کا زرعی مددگار</Text>
          </View>

          <View style={styles.cardsContainer}>
            <TouchableOpacity
              style={styles.homeCard}
              activeOpacity={0.8}
              onPress={() => setCurrentScreen('Chat')}
            >
              <View style={[styles.cardIcon, { backgroundColor: '#f0f9f2' }]}>
                <Text style={styles.cardEmoji}>💬</Text>
              </View>
              <View style={styles.cardTextContainer}>
                <Text style={styles.cardTitle}>گفتگو</Text>
                <Text style={styles.cardSubtitle}>
                  فصل کے مسئلے کے بارے میں پوچھیں
                </Text>
              </View>
              <Text style={styles.cardArrow}>‹</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.homeCard}
              activeOpacity={0.8}
              onPress={() => setCurrentScreen('Weather')}
            >
              <View style={[styles.cardIcon, { backgroundColor: '#fff8ee' }]}>
                <Text style={styles.cardEmoji}>🌤️</Text>
              </View>
              <View style={styles.cardTextContainer}>
                <Text style={styles.cardTitle}>موسم</Text>
                <Text style={styles.cardSubtitle}>
                  اپنے علاقے کا موسم دیکھیں
                </Text>
              </View>
              <Text style={styles.cardArrow}>‹</Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.homeFooter}>
            کسان AI v1.0 — پاکستانی کسانوں کے لیے 🇵🇰
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  // ─── WEATHER SCREEN ───
  if (currentScreen === 'Weather') {
    // Extract weather and irrigation data from latest result if available
    const weatherData =
      currentWeatherData ||
      result?.weather ||
      result?.weather_data ||
      result?.weather_info ||
      null;
    const irrigationAdvice = result?.irrigation_advice || null;
    const locationName =
      currentLocationName ||
      result?.location ||
      weatherData?.location ||
      null;

    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="dark-content" backgroundColor="#f2f0ec" />
        <View style={styles.screenHeader}>
          <TouchableOpacity
            onPress={() => setCurrentScreen('Home')}
            style={styles.backBtn}
          >
            <Text style={styles.backText}>→ واپس</Text>
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={styles.screenTitle}>🌤️ موسم</Text>
          </View>
          <View style={styles.headerSpacer} />
        </View>
        <WeatherCard
          weatherData={weatherData}
          locationName={locationName}
          irrigationAdvice={irrigationAdvice}
        />
      </SafeAreaView>
    );
  }

  // ─── CHAT SCREEN ───
  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="dark-content" backgroundColor="#ffffff" />

      {/* Chat Header */}
      <View style={styles.chatHeader}>
        <TouchableOpacity
          onPress={() => setCurrentScreen('Home')}
          style={styles.backBtn}
        >
          <Text style={styles.backText}>→ واپس</Text>
        </TouchableOpacity>
        <View style={styles.chatHeaderCenter}>
          <Text style={styles.chatHeaderTitle}>💬 گفتگو</Text>
          <Text style={styles.chatHeaderSub}>کسان AI سے مدد لیں</Text>
        </View>
        {/* Clear Chat */}
        <TouchableOpacity
          onPress={clearChat}
          style={styles.clearChatBtn}
          activeOpacity={0.7}
        >
          <Text style={styles.clearChatText}>🗑️ صاف کریں</Text>
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView
        style={styles.chatBody}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 0}
      >
        {/* Messages Area */}
        <ScrollView
          ref={scrollViewRef}
          style={styles.messagesArea}
          contentContainerStyle={styles.messagesContent}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() =>
            scrollViewRef.current?.scrollToEnd({ animated: true })
          }
        >
          {chatMessages.length === 0 && (
            <View style={styles.emptyChat}>
              <Text style={styles.emptyChatIcon}>🌾</Text>
              <Text style={styles.emptyChatText}>
                کسان AI میں خوش آمدید!
              </Text>
              <Text style={styles.emptyChatSub}>
                اپنی فصل کا مسئلہ نیچے لکھیں یا تصویر بھیجیں
              </Text>
            </View>
          )}

          {chatMessages.map((msg) => {
            if (msg.type === 'user') {
              const isImageOnly = msg.isImageOnly || !msg.text || msg.text === 'تصویر بھیجی گئی';
              return (
                <View
                  key={msg.id}
                  style={[
                    styles.userBubble,
                    isImageOnly && msg.image && styles.userBubbleImageOnly
                  ]}
                >
                  {msg.image ? (
                    <MessageImage uri={msg.image} isImageOnly={isImageOnly} />
                  ) : null}
                  {!isImageOnly ? (
                    <Text style={styles.userBubbleText}>{msg.text}</Text>
                  ) : null}
                </View>
              );
            }

            if (msg.type === 'error') {
              return (
                <View key={msg.id} style={styles.errorBubble}>
                  <Text style={styles.errorBubbleText}>⚠️ {msg.text}</Text>
                </View>
              );
            }

            if (msg.type === 'ai') {
              const isUrdu = containsUrdu(msg.text);
              const status = ttsStatus[msg.id];
              
              let ttsButtonText = "سنیں 🔊";
              let isTtsLoading = false;
              let isTtsPlaying = false;
              let isTtsError = false;

              if (status === 'loading') {
                ttsButtonText = "آواز تیار ہو رہی ہے...";
                isTtsLoading = true;
              } else if (status === 'playing') {
                ttsButtonText = "بند کریں ⏹️";
                isTtsPlaying = true;
              } else if (status === 'error') {
                ttsButtonText = "دوبارہ کوشش کریں 🔊";
                isTtsError = true;
              }

              const langHint = msg.data?.input_summary?.language_hint || null;

              return (
                <View key={msg.id} style={styles.aiBubble}>
                  <Text style={[
                    styles.aiBubbleText,
                    !isUrdu && { textAlign: 'left', writingDirection: 'ltr' }
                  ]}>{msg.text}</Text>
                  
                  {/* TTS Button */}
                  <View style={styles.ttsButtonContainer}>
                    <TouchableOpacity
                      onPress={() => handlePlayTTS(msg.id, msg.ttsSummary || getShortenedSummary(msg.text), langHint, msg.audioUrl)}
                      style={[
                        styles.ttsButton,
                        isTtsLoading && styles.ttsButtonLoading,
                        isTtsPlaying && styles.ttsButtonPlaying,
                        isTtsError && styles.ttsButtonError,
                      ]}
                      disabled={isTtsLoading}
                      activeOpacity={0.7}
                    >
                      <Text style={styles.ttsButtonText}>{ttsButtonText}</Text>
                    </TouchableOpacity>
                  </View>

                  {/* Show error notification message below if TTS failed */}
                  {isTtsError && (
                    <Text style={styles.ttsErrorHintText}>
                      آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔
                    </Text>
                  )}
                </View>
              );
            }

            return null;
          })}

          {loading && <LoadingSpinner message={loadingMessage} />}
        </ScrollView>

        {/* Bottom Input */}
        <MultimodalInput onSubmit={handleSubmit} isLoading={loading} />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#f2f0ec',
    paddingTop: Platform.OS === 'android' ? StatusBar.currentHeight : 0,
  },

  // ─── HOME ───
  homeContainer: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  homeHeader: {
    alignItems: 'center',
    marginBottom: 40,
  },
  homeTitle: {
    fontSize: 36,
    fontWeight: '800',
    color: '#1a7a2e',
    marginBottom: 6,
  },
  homeSubtitle: {
    fontSize: 16,
    color: '#888',
  },
  cardsContainer: {
    gap: 14,
  },
  homeCard: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    padding: 20,
    flexDirection: 'row-reverse',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.07,
    shadowRadius: 8,
    elevation: 3,
  },
  cardIcon: {
    width: 52,
    height: 52,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 16,
  },
  cardEmoji: {
    fontSize: 26,
  },
  cardTextContainer: {
    flex: 1,
    alignItems: 'flex-end',
  },
  cardTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#333',
    marginBottom: 3,
  },
  cardSubtitle: {
    fontSize: 13,
    color: '#999',
    textAlign: 'right',
  },
  cardArrow: {
    fontSize: 24,
    color: '#ccc',
    marginRight: 4,
  },
  homeFooter: {
    textAlign: 'center',
    fontSize: 12,
    color: '#ccc',
    marginTop: 40,
  },

  // ─── SCREEN HEADERS ───
  screenHeader: {
    backgroundColor: '#ffffff',
    flexDirection: 'row-reverse',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#e8e8e5',
  },
  backBtn: {
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  backText: {
    fontSize: 15,
    color: '#1a7a2e',
    fontWeight: '600',
  },
  headerCenter: {
    flex: 1,
    alignItems: 'center',
  },
  headerSpacer: {
    width: 60,
  },
  screenTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#333',
  },

  // ─── CHAT ───
  chatHeader: {
    backgroundColor: '#ffffff',
    flexDirection: 'row-reverse',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#e8e8e5',
  },
  chatHeaderCenter: {
    flex: 1,
    alignItems: 'center',
  },
  chatHeaderTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#333',
  },
  chatHeaderSub: {
    fontSize: 12,
    color: '#999',
    marginTop: 1,
  },
  clearChatBtn: {
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 12,
    backgroundColor: '#fef2f2',
  },
  clearChatText: {
    fontSize: 12,
    color: '#b91c1c',
    fontWeight: '600',
  },
  chatBody: {
    flex: 1,
  },
  messagesArea: {
    flex: 1,
    backgroundColor: '#f2f0ec',
  },
  messagesContent: {
    paddingVertical: 16,
    paddingBottom: 8,
  },

  // Empty state
  emptyChat: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 80,
    paddingHorizontal: 40,
  },
  emptyChatIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  emptyChatText: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1a7a2e',
    marginBottom: 8,
    textAlign: 'center',
  },
  emptyChatSub: {
    fontSize: 14,
    color: '#999',
    textAlign: 'center',
    lineHeight: 22,
  },

  // Chat bubbles
  userBubble: {
    backgroundColor: '#1a7a2e',
    borderRadius: 18,
    borderTopRightRadius: 4,
    padding: 14,
    marginLeft: 50,
    marginRight: 12,
    marginVertical: 4,
    maxWidth: '80%',
    alignSelf: 'flex-end',
  },
  userBubbleImageOnly: {
    backgroundColor: 'transparent',
    padding: 0,
    borderRadius: 12,
  },
  userBubbleImage: {
    width: 240,
    height: 180,
    borderRadius: 12,
    marginBottom: 8,
    resizeMode: 'cover',
  },
  imageErrorContainer: {
    width: 240,
    height: 180,
    backgroundColor: '#f8d7da',
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#f5c6cb',
  },
  imageErrorText: {
    color: '#721c24',
    fontSize: 14,
    fontWeight: '600',
    textAlign: 'center',
    paddingHorizontal: 10,
  },
  userBubbleText: {
    color: '#ffffff',
    fontSize: 15,
    lineHeight: 22,
    textAlign: 'right',
    writingDirection: 'rtl',
    flexShrink: 1,
    flexWrap: 'wrap',
  },
  aiBubble: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    borderTopLeftRadius: 4,
    padding: 14,
    marginRight: 50,
    marginLeft: 12,
    marginVertical: 4,
    maxWidth: '85%',
    alignSelf: 'flex-start',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  aiBubbleText: {
    fontSize: 15,
    color: '#333',
    lineHeight: 24,
    textAlign: 'right',
    writingDirection: 'rtl',
    flexShrink: 1,
    flexWrap: 'wrap',
  },
  errorBubble: {
    backgroundColor: '#fef2f2',
    borderRadius: 14,
    padding: 12,
    marginHorizontal: 12,
    marginVertical: 4,
    borderWidth: 1,
    borderColor: '#fecaca',
  },
  errorBubbleText: {
    fontSize: 14,
    color: '#b91c1c',
    textAlign: 'right',
    lineHeight: 20,
    writingDirection: 'rtl',
    flexWrap: 'wrap',
  },
  ttsButtonContainer: {
    marginTop: 8,
    flexDirection: 'row',
    justifyContent: 'flex-end',
    width: '100%',
  },
  ttsButton: {
    backgroundColor: '#f0fdf4',
    borderColor: '#bbf7d0',
    borderWidth: 1,
    borderRadius: 12,
    paddingVertical: 5,
    paddingHorizontal: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ttsButtonLoading: {
    backgroundColor: '#f3f4f6',
    borderColor: '#e5e7eb',
  },
  ttsButtonPlaying: {
    backgroundColor: '#fee2e2',
    borderColor: '#fca5a5',
  },
  ttsButtonError: {
    backgroundColor: '#fff1f2',
    borderColor: '#fecdd3',
  },
  ttsButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#1a7a2e',
    textAlign: 'right',
  },
  ttsErrorHintText: {
    fontSize: 11,
    color: '#dc2626',
    marginTop: 4,
    textAlign: 'right',
    writingDirection: 'rtl',
    width: '100%',
  },
});
