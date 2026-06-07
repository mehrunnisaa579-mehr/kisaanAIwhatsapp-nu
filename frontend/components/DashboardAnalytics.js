import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { getRiskLabel } from '../utils/formatter';

export default function DashboardAnalytics({ data, inspectionCount }) {
  const inputSummary = data?.input_summary;
  const diagnosis = data?.diagnosis;

  const metrics = [
    {
      label: 'کل جائزے',
      value: String(inspectionCount),
      icon: '📊',
    },
    {
      label: 'خطرے کی سطح',
      value: diagnosis ? getRiskLabel(diagnosis.risk_level) : '—',
      icon: '⚠️',
    },
    {
      label: 'تصویر موصول',
      value: inputSummary?.image_received ? 'ہاں ✅' : 'نہیں',
      icon: '📷',
    },
    {
      label: 'مقام موصول',
      value: inputSummary?.location_received ? 'ہاں ✅' : 'نہیں',
      icon: '📍',
    },
  ];

  return (
    <ScrollView
      style={styles.scrollView}
      contentContainerStyle={styles.scrollContent}
      showsVerticalScrollIndicator={false}
    >
      <Text style={styles.heading}>📈 ڈیش بورڈ</Text>
      <Text style={styles.subtitle}>آپ کے زرعی جائزوں کا خلاصہ</Text>

      <View style={styles.metricsGrid}>
        {metrics.map((metric, index) => (
          <View key={index} style={styles.metricItem}>
            <Text style={styles.metricIcon}>{metric.icon}</Text>
            <Text style={styles.metricValue}>{metric.value}</Text>
            <Text style={styles.metricLabel}>{metric.label}</Text>
          </View>
        ))}
      </View>

      <View style={styles.infoCard}>
        <Text style={styles.infoIcon}>💡</Text>
        <Text style={styles.infoText}>
          مزید تفصیلات جلد دستیاب ہوں گی۔ گفتگو سیکشن میں فصل کا مسئلہ بھیجیں۔
        </Text>
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
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginBottom: 16,
  },
  metricItem: {
    width: '47%',
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
  metricIcon: {
    fontSize: 28,
    marginBottom: 8,
  },
  metricValue: {
    fontSize: 16,
    fontWeight: '700',
    color: '#333',
    marginBottom: 4,
    textAlign: 'center',
  },
  metricLabel: {
    fontSize: 13,
    color: '#888',
    fontWeight: '500',
    textAlign: 'center',
  },
  infoCard: {
    backgroundColor: '#fff8ee',
    borderRadius: 14,
    padding: 16,
    flexDirection: 'row-reverse',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#f5deb3',
  },
  infoIcon: {
    fontSize: 22,
    marginLeft: 12,
  },
  infoText: {
    flex: 1,
    fontSize: 13,
    color: '#8b7355',
    textAlign: 'right',
    lineHeight: 20,
    writingDirection: 'rtl',
    flexWrap: 'wrap',
  },
});
