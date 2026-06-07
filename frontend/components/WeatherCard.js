import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';

/**
 * WeatherCard — displays weather data with spray and water advice.
 *
 * Props (all optional — component uses fallback when absent):
 *   weatherData: { temperature, humidity, wind, condition, rain_expected,
 *                  spray_safe, rain_probability, forecast }
 *   locationName: string   e.g. "ملتان، پاکستان"
 *   irrigationAdvice: { message } — backend irrigation_advice object
 */
export default function WeatherCard({ weatherData, locationName, irrigationAdvice }) {
  const weather = weatherData || {};
  const isMock = !weatherData;

  // ── Values ──
  const temp = weather.temperature ?? '—';
  const humidity = weather.humidity ?? '—';
  const displayLocation = locationName || weather.location || 'مقام دستیاب نہیں';

  // ── Rain status ──
  const hasWeatherInfo =
    weather.rain_expected !== undefined ||
    weather.rain_probability !== undefined ||
    weather.humidity !== undefined;

  let rainText = 'معلومات دستیاب نہیں';
  if (hasWeatherInfo) {
    rainText = weather.rain_expected === true ? 'متوقع' : 'متوقع نہیں';
  }

  // ── Spray advice ──
  let sprayIcon = 'ℹ️';
  let sprayText = 'موسم کی معلومات دستیاب نہیں، پانی یا سپرے سے پہلے مقامی موسم ضرور چیک کریں';

  if (hasWeatherInfo || !isMock) {
    if (weather.spray_safe === false || weather.rain_expected === true) {
      sprayIcon = '⚠️';
      sprayText = 'بارش کی وجہ سے سپرے مؤخر کریں';
    } else {
      sprayIcon = '✅';
      sprayText = 'موسم مناسب ہو تو سپرے کیا جا سکتا ہے';
    }
  }

  // ── Water / irrigation advice ──
  let waterIcon = 'ℹ️';
  let waterText =
    'موسم کی معلومات دستیاب نہیں، پانی یا سپرے سے پہلے مقامی موسم ضرور چیک کریں';

  // Use backend irrigation_advice.message if provided
  if (irrigationAdvice?.message) {
    waterIcon = '💧';
    waterText = irrigationAdvice.message;
  } else if (hasWeatherInfo) {
    if (weather.rain_expected === true) {
      waterIcon = '🌧️';
      waterText = 'ابھی پانی نہ دیں';
    } else {
      waterIcon = '💧';
      waterText = 'اگر زمین خشک ہے تو ہلکا پانی دیا جا سکتا ہے';
    }
  }

  return (
    <ScrollView
      style={styles.scrollView}
      contentContainerStyle={styles.scrollContent}
      showsVerticalScrollIndicator={false}
    >
      <Text style={styles.heading}>🌤️ موسم</Text>
      <Text style={styles.subtitle}>آپ کے علاقے کا موسم</Text>

      {/* Location */}
      <View style={styles.locationCard}>
        <Text style={styles.locationIcon}>📍</Text>
        <View style={styles.locationContent}>
          <Text style={styles.locationLabel}>مقام</Text>
          <Text style={styles.locationText}>{displayLocation}</Text>
        </View>
      </View>

      {/* Temperature */}
      <View style={styles.mainTemp}>
        <Text style={styles.tempValue}>{temp}</Text>
        <Text style={styles.tempLabel}>درجہ حرارت</Text>
      </View>

      {/* Humidity & Rain */}
      <View style={styles.detailsRow}>
        <View style={styles.detailCard}>
          <Text style={styles.detailIcon}>💧</Text>
          <Text style={styles.detailValue}>{humidity}</Text>
          <Text style={styles.detailLabel}>نمی</Text>
        </View>

        <View style={styles.detailCard}>
          <Text style={styles.detailIcon}>🌧️</Text>
          <Text style={styles.detailValue}>{rainText}</Text>
          <Text style={styles.detailLabel}>بارش</Text>
        </View>
      </View>

      {/* Spray advice */}
      <View
        style={[
          styles.adviceCard,
          {
            backgroundColor:
              sprayIcon === '⚠️' ? '#fff8ee' : sprayIcon === '✅' ? '#f0f9f2' : '#f7f7f5',
            borderColor:
              sprayIcon === '⚠️' ? '#f5deb3' : sprayIcon === '✅' ? '#d4eeda' : '#e8e8e5',
          },
        ]}
      >
        <Text style={styles.adviceIcon}>{sprayIcon}</Text>
        <View style={styles.adviceContent}>
          <Text style={styles.adviceTitle}>سپرے کا مشورہ</Text>
          <Text style={styles.adviceSub}>{sprayText}</Text>
        </View>
      </View>

      {/* Water / irrigation advice */}
      <View
        style={[
          styles.adviceCard,
          {
            backgroundColor:
              waterIcon === '🌧️' ? '#fff8ee' : waterIcon === '💧' ? '#f0f9f2' : '#f7f7f5',
            borderColor:
              waterIcon === '🌧️' ? '#f5deb3' : waterIcon === '💧' ? '#d4eeda' : '#e8e8e5',
          },
        ]}
      >
        <Text style={styles.adviceIcon}>{waterIcon}</Text>
        <View style={styles.adviceContent}>
          <Text style={styles.adviceTitle}>پانی کا مشورہ</Text>
          <Text style={styles.adviceSub}>{waterText}</Text>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollView: {
    flex: 1,
    backgroundColor: '#f2f0ec',
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 40,
  },
  heading: {
    fontSize: 24,
    fontWeight: '800',
    color: '#1a7a2e',
    textAlign: 'right',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 14,
    color: '#888',
    textAlign: 'right',
    marginBottom: 24,
  },

  // ─── Location ───
  locationCard: {
    backgroundColor: '#ffffff',
    borderRadius: 14,
    padding: 14,
    flexDirection: 'row-reverse',
    alignItems: 'center',
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
  locationIcon: {
    fontSize: 18,
    marginLeft: 10,
  },
  locationContent: {
    flex: 1,
    alignItems: 'flex-end',
  },
  locationLabel: {
    fontSize: 11,
    color: '#888',
    fontWeight: '600',
    marginBottom: 2,
  },
  locationText: {
    fontSize: 14,
    color: '#333',
    fontWeight: '600',
    textAlign: 'right',
    writingDirection: 'rtl',
  },

  // ─── Temperature ───
  mainTemp: {
    backgroundColor: '#ffffff',
    borderRadius: 20,
    padding: 30,
    alignItems: 'center',
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
  },
  tempValue: {
    fontSize: 48,
    fontWeight: '800',
    color: '#1a7a2e',
  },
  tempLabel: {
    fontSize: 16,
    color: '#888',
    marginTop: 4,
  },

  // ─── Detail cards ───
  detailsRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 16,
  },
  detailCard: {
    flex: 1,
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 18,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
  detailIcon: {
    fontSize: 26,
    marginBottom: 8,
  },
  detailValue: {
    fontSize: 18,
    fontWeight: '700',
    color: '#333',
    marginBottom: 4,
    textAlign: 'center',
  },
  detailLabel: {
    fontSize: 13,
    color: '#888',
  },

  // ─── Advice cards (spray + water) ───
  adviceCard: {
    borderRadius: 16,
    padding: 18,
    flexDirection: 'row-reverse',
    alignItems: 'center',
    marginBottom: 12,
    borderWidth: 1,
  },
  adviceIcon: {
    fontSize: 28,
    marginLeft: 14,
  },
  adviceContent: {
    flex: 1,
    flexShrink: 1,
  },
  adviceTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#1a7a2e',
    textAlign: 'right',
    writingDirection: 'rtl',
    flexWrap: 'wrap',
  },
  adviceSub: {
    fontSize: 13,
    color: '#666',
    textAlign: 'right',
    marginTop: 4,
    lineHeight: 20,
    writingDirection: 'rtl',
    flexWrap: 'wrap',
  },
});
