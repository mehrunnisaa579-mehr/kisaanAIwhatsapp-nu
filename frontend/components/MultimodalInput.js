import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  Image,
  StyleSheet,
  Alert,
  Modal,
  Pressable,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Audio } from 'expo-av';

export default function MultimodalInput({ onSubmit, isLoading }) {
  const [text, setText] = useState('');
  const [imageUri, setImageUri] = useState(null);
  const [showMediaModal, setShowMediaModal] = useState(false);
  const [recording, setRecording] = useState(null);
  const [isRecording, setIsRecording] = useState(false);

  useEffect(() => {
    return () => {
      if (recording) {
        recording.stopAndUnloadAsync().catch(() => {});
      }
    };
  }, [recording]);

  const startRecording = async () => {
    try {
      console.log('Requesting microphone permissions...');
      const { status } = await Audio.requestPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('اجازت درکار', 'آواز ریکارڈ کرنے کے لیے مائیکروفون کی اجازت ضروری ہے۔');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      console.log('Starting recording...');
      const { recording: newRecording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );
      setRecording(newRecording);
      setIsRecording(true);
      console.log('Recording started');
    } catch (err) {
      console.error('Failed to start recording', err);
      Alert.alert('غلطی', 'ریکارڈنگ شروع کرنے میں ناکامی ہوئی۔');
    }
  };

  const stopRecording = async () => {
    if (!recording) return;
    try {
      console.log('Stopping recording...');
      setIsRecording(false);
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      console.log('Recording stopped and stored at', uri);
      setRecording(null);
      
      if (uri) {
        onSubmit({
          text: '',
          crop: '',
          image: null,
          voiceUri: uri,
          latitude: null,
          longitude: null,
        });
      } else {
        Alert.alert('غلطی', 'آواز موصول نہیں ہوئی۔ براہ کرم دوبارہ ریکارڈ کریں۔');
      }
    } catch (err) {
      console.error('Failed to stop recording', err);
      Alert.alert('غلطی', 'ریکارڈنگ روکنے میں ناکامی ہوئی۔');
      setIsRecording(false);
      setRecording(null);
    }
  };

  const pickImage = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('اجازت درکار', 'گیلری تک رسائی ضروری ہے۔');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: false,
      quality: 0.7,
    });
    if (!result.canceled && result.assets && result.assets.length > 0) {
      setImageUri(result.assets[0].uri);
    }
  };

  const takePhoto = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('اجازت درکار', 'کیمرہ تک رسائی ضروری ہے۔');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      allowsEditing: false,
      quality: 0.7,
    });
    if (!result.canceled && result.assets && result.assets.length > 0) {
      setImageUri(result.assets[0].uri);
    }
  };

  const handleSubmit = () => {
    if (!text.trim() && !imageUri) {
      Alert.alert('ان پٹ ضروری ہے', 'کچھ لکھیں یا تصویر بھیجیں!');
      return;
    }
    onSubmit({
      text: text.trim(),
      crop: '',
      image: imageUri,
      latitude: null,
      longitude: null,
    });
    setText('');
    setImageUri(null);
  };

  const removeImage = () => {
    setImageUri(null);
  };

  const handleMicPress = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const handleMediaOption = (option) => {
    setShowMediaModal(false);
    setTimeout(() => {
      if (option === 'gallery') {
        pickImage();
      } else if (option === 'camera') {
        takePhoto();
      }
    }, 300);
  };

  return (
    <View style={styles.container}>
      {/* Image Preview & Custom Send Button */}
      {imageUri && (
        <View style={styles.imagePreviewContainer}>
          <View style={styles.imagePreviewRow}>
            <Image source={{ uri: imageUri }} style={styles.imagePreview} />
            <TouchableOpacity style={styles.removeImageBtn} onPress={removeImage}>
              <Text style={styles.removeImageText}>✕</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity
            style={styles.imageSendBtn}
            onPress={handleSubmit}
            disabled={isLoading}
            activeOpacity={0.7}
          >
            <Text style={styles.imageSendBtnText}>تصویر بھیجیں</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Input Row: [Camera] [Input] [Mic] [Send] */}
      <View style={styles.inputRow}>
        {/* Camera button — left side */}
        <TouchableOpacity
          style={styles.cameraBtn}
          onPress={() => setShowMediaModal(true)}
          activeOpacity={0.7}
        >
          <Text style={styles.cameraBtnIcon}>📷</Text>
        </TouchableOpacity>

        {/* Message input — center */}
        <TextInput
          style={[styles.textInput, isRecording && { color: '#e74c3c' }]}
          placeholder={isRecording ? "ریکارڈنگ جاری ہے..." : "اپنا مسئلہ لکھیں..."}
          placeholderTextColor={isRecording ? "#e74c3c" : "#aaa"}
          value={isRecording ? "" : text}
          onChangeText={setText}
          editable={!isRecording && !isLoading}
          multiline
          textAlignVertical="center"
          writingDirection="rtl"
        />

        {/* Mic button — beside send */}
        <TouchableOpacity
          style={[styles.micBtn, isRecording && { backgroundColor: '#e74c3c' }]}
          onPress={handleMicPress}
          disabled={isLoading}
          activeOpacity={0.7}
        >
          <Text style={styles.micBtnIcon}>{isRecording ? "⏹️" : "🎙️"}</Text>
        </TouchableOpacity>

        {/* Send button — far right */}
        <TouchableOpacity
          style={[styles.sendBtn, isLoading && styles.sendBtnDisabled]}
          onPress={handleSubmit}
          disabled={isLoading}
          activeOpacity={0.7}
        >
          <Text style={styles.sendIcon}>➤</Text>
        </TouchableOpacity>
      </View>

      {/* Camera/Gallery Bottom Sheet Modal */}
      <Modal
        visible={showMediaModal}
        transparent
        animationType="slide"
        onRequestClose={() => setShowMediaModal(false)}
      >
        <Pressable
          style={styles.modalOverlay}
          onPress={() => setShowMediaModal(false)}
        >
          <Pressable style={styles.modalSheet} onPress={() => {}}>
            <View style={styles.modalHandle} />
            <Text style={styles.modalTitle}>تصویر منتخب کریں</Text>

            <TouchableOpacity
              style={styles.modalOption}
              onPress={() => handleMediaOption('gallery')}
              activeOpacity={0.7}
            >
              <View style={styles.modalOptionIconWrap}>
                <Text style={styles.modalOptionIcon}>🖼️</Text>
              </View>
              <Text style={styles.modalOptionText}>
                گیلری سے تصویر منتخب کریں
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.modalOption}
              onPress={() => handleMediaOption('camera')}
              activeOpacity={0.7}
            >
              <View style={styles.modalOptionIconWrap}>
                <Text style={styles.modalOptionIcon}>📷</Text>
              </View>
              <Text style={styles.modalOptionText}>کیمرے سے تصویر لیں</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.modalCancel}
              onPress={() => setShowMediaModal(false)}
              activeOpacity={0.7}
            >
              <Text style={styles.modalCancelText}>واپس جائیں</Text>
            </TouchableOpacity>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderTopColor: '#e8e8e5',
    paddingHorizontal: 8,
    paddingTop: 8,
    paddingBottom: 10,
  },
  imagePreviewContainer: {
    backgroundColor: '#f9f9f7',
    borderRadius: 14,
    padding: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#e8e8e5',
    alignItems: 'center',
    width: '100%',
  },
  imagePreviewRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
    paddingHorizontal: 4,
    width: '100%',
    justifyContent: 'center',
  },
  imageSendBtn: {
    backgroundColor: '#1a7a2e',
    borderRadius: 12,
    paddingVertical: 10,
    paddingHorizontal: 24,
    marginTop: 6,
    width: '100%',
    alignItems: 'center',
  },
  imageSendBtnText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '700',
  },
  imagePreview: {
    width: 60,
    height: 60,
    borderRadius: 10,
  },
  removeImageBtn: {
    marginLeft: 8,
    backgroundColor: '#e74c3c',
    borderRadius: 12,
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  removeImageText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '700',
  },

  // ─── Input Row ───
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 6,
  },
  cameraBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#f0f0ee',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cameraBtnIcon: {
    fontSize: 20,
  },
  textInput: {
    flex: 1,
    backgroundColor: '#f7f7f5',
    borderRadius: 22,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
    color: '#333',
    maxHeight: 100,
    borderWidth: 1,
    borderColor: '#e8e8e5',
    textAlign: 'right',
  },
  micBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#1a5c28',
    alignItems: 'center',
    justifyContent: 'center',
  },
  micBtnIcon: {
    fontSize: 18,
    color: '#ffffff',
  },
  sendBtn: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: '#1a7a2e',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: {
    backgroundColor: '#88c494',
  },
  sendIcon: {
    color: '#fff',
    fontSize: 20,
  },

  // ─── Media Picker Modal ───
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    backgroundColor: '#ffffff',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: 20,
    paddingBottom: 34,
    paddingTop: 12,
  },
  modalHandle: {
    width: 40,
    height: 4,
    backgroundColor: '#ddd',
    borderRadius: 2,
    alignSelf: 'center',
    marginBottom: 18,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#333',
    textAlign: 'right',
    marginBottom: 16,
    writingDirection: 'rtl',
  },
  modalOption: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    backgroundColor: '#f7f7f5',
    borderRadius: 16,
    padding: 16,
    marginBottom: 10,
  },
  modalOptionIconWrap: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: '#f0f9f2',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 14,
  },
  modalOptionIcon: {
    fontSize: 24,
  },
  modalOptionText: {
    flex: 1,
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    textAlign: 'right',
    writingDirection: 'rtl',
    flexShrink: 1,
    flexWrap: 'wrap',
    paddingHorizontal: 4,
  },
  modalCancel: {
    alignItems: 'center',
    paddingVertical: 14,
    marginTop: 4,
  },
  modalCancelText: {
    fontSize: 15,
    color: '#999',
    fontWeight: '600',
  },
});
