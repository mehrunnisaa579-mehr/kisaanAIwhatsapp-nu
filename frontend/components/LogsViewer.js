import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';

export default function LogsViewer({ logs }) {
  const [expanded, setExpanded] = useState(false);

  if (!logs || !Array.isArray(logs) || logs.length === 0) return null;

  return (
    <View style={styles.bubble}>
      <TouchableOpacity
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.7}
        style={styles.toggleRow}
      >
        <Text style={styles.toggleIcon}>{expanded ? '▲' : '▼'}</Text>
        <Text style={styles.heading}>📋 تکنیکی تفصیل</Text>
      </TouchableOpacity>

      {expanded && (
        <ScrollView style={styles.logsContainer} nestedScrollEnabled>
          {logs.map((log, index) => (
            <View key={index} style={styles.logItem}>
              <Text style={styles.logText}>{JSON.stringify(log, null, 2)}</Text>
            </View>
          ))}
        </ScrollView>
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
  logsContainer: {
    maxHeight: 160,
    marginTop: 10,
  },
  logItem: {
    backgroundColor: '#f7f7f5',
    borderRadius: 8,
    padding: 8,
    marginBottom: 4,
  },
  logText: {
    fontSize: 11,
    color: '#555',
    fontFamily: 'monospace',
  },
});
