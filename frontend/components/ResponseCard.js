import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import {
  formatConfidence,
  getRiskLabel,
  formatCropUrdu,
  formatDiseaseUrdu,
  formatRiskUrdu,
} from '../utils/formatter';

const containsUrdu = (text) => {
  if (!text) return false;
  const urduCount = (text.match(/[\u0600-\u06FF]/g) || []).length;
  const latinCount = (text.match(/[a-zA-Z]/g) || []).length;
  return urduCount > latinCount;
};

export default function ResponseCard({ data }) {
  if (!data) return null;

  const diagnosis = data?.diagnosis;
  const farmerResponse =
    data?.farmer_response ||
    data?.response ||
    data?.message ||
    'جواب موصول ہو گیا ہے۔';

  // Urdu-mapped values
  const cropUrdu = formatCropUrdu(diagnosis?.crop);
  const diseaseUrdu = formatDiseaseUrdu(diagnosis?.disease, diagnosis?.disease_urdu);
  const riskUrdu = getRiskLabel(diagnosis?.risk_level);
  const confidenceUrdu = formatConfidence(diagnosis?.confidence);

  const isUrdu = containsUrdu(farmerResponse);

  return (
    <View style={styles.bubble}>
      <Text style={[
        styles.farmerResponse,
        !isUrdu && { textAlign: 'left', writingDirection: 'ltr' }
      ]}>{farmerResponse}</Text>

      {diagnosis && (
        <View style={styles.diagGrid}>
          <View style={styles.diagItem}>
            <Text style={styles.diagLabel}>فصل</Text>
            <Text style={styles.diagValue}>{cropUrdu}</Text>
          </View>

          <View style={styles.diagItem}>
            <Text style={styles.diagLabel}>بیماری</Text>
            <Text style={styles.diagValueDisease}>{diseaseUrdu}</Text>
          </View>

          {diagnosis.confidence !== null && diagnosis.confidence !== undefined ? (
            <View style={styles.diagItem}>
              <Text style={styles.diagLabel}>اعتماد</Text>
              <Text style={styles.diagValue}>{confidenceUrdu}</Text>
            </View>
          ) : null}

          <View style={styles.diagItem}>
            <Text style={styles.diagLabel}>خطرہ</Text>
            <Text style={styles.diagValueRisk}>{riskUrdu}</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    borderTopLeftRadius: 4,
    padding: 14,
    marginRight: 50,
    marginLeft: 12,
    marginVertical: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  farmerResponse: {
    fontSize: 15,
    color: '#333',
    lineHeight: 24,
    textAlign: 'right',
    writingDirection: 'rtl',
    marginBottom: 10,
    flexShrink: 1,
    flexWrap: 'wrap',
  },
  diagGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  diagItem: {
    width: '47%',
    backgroundColor: '#f0f9f2',
    borderRadius: 10,
    padding: 10,
    alignItems: 'center',
  },
  diagLabel: {
    fontSize: 11,
    color: '#888',
    fontWeight: '600',
    marginBottom: 3,
  },
  diagValue: {
    fontSize: 14,
    color: '#333',
    fontWeight: '700',
    textAlign: 'center',
    flexWrap: 'wrap',
  },
  diagValueDisease: {
    fontSize: 13,
    color: '#c0392b',
    fontWeight: '600',
    textAlign: 'center',
    flexWrap: 'wrap',
  },
  diagValueRisk: {
    fontSize: 13,
    fontWeight: '700',
    textAlign: 'center',
    flexWrap: 'wrap',
  },
});
