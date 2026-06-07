import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { mapActionStepUrdu } from '../utils/formatter';

export default function ActionChainCard({ actionChain }) {
  const [expanded, setExpanded] = useState(false);

  if (!actionChain || actionChain.length === 0) return null;

  const getStatusIcon = (status) => {
    if (status === 'success') return '✅';
    if (status === 'pending') return '⏳';
    if (status === 'error') return '❌';
    return '⬜';
  };

  return (
    <View style={styles.bubble}>
      <TouchableOpacity
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.7}
        style={styles.toggleRow}
      >
        <Text style={styles.toggleIcon}>{expanded ? '▲' : '▼'}</Text>
        <Text style={styles.heading}>⚙️ تفصیل دیکھیں</Text>
      </TouchableOpacity>

      {expanded && (
        <View style={styles.stepsContainer}>
          {actionChain.map((item, index) => (
            <View key={index} style={styles.stepRow}>
              <Text style={styles.statusIcon}>
                {getStatusIcon(item.status)}
              </Text>
              <Text style={styles.stepText}>
                {mapActionStepUrdu(index)}
              </Text>
            </View>
          ))}
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
  toggleRow: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    justifyContent: 'flex-start',
  },
  heading: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1a7a2e',
    textAlign: 'right',
    writingDirection: 'rtl',
  },
  toggleIcon: {
    fontSize: 12,
    color: '#1a7a2e',
    marginRight: 8,
  },
  stepsContainer: {
    marginTop: 10,
  },
  stepRow: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    backgroundColor: '#f7f7f5',
    borderRadius: 10,
    padding: 10,
    marginBottom: 6,
  },
  stepText: {
    flex: 1,
    fontSize: 13,
    color: '#555',
    textAlign: 'right',
    writingDirection: 'rtl',
    marginRight: 8,
    flexWrap: 'wrap',
  },
  statusIcon: {
    fontSize: 16,
    marginLeft: 6,
  },
});
