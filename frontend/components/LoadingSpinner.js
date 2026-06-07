import React from 'react';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';

export default function LoadingSpinner({ message }) {
  return (
    <View style={styles.container}>
      <ActivityIndicator size="large" color="#2d9e4f" />
      <Text style={styles.text}>
        {message || "کسان AI آپ کی فصل کا مسئلہ جانچ رہا ہے..."}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 24,
  },
  text: {
    marginTop: 14,
    fontSize: 15,
    color: '#888',
    textAlign: 'center',
    lineHeight: 24,
  },
});
