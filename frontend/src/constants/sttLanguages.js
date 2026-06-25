export function fileEntryKey(file) {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

export function languageLabel(code) {
  const labels = {
    'ta-IN': 'Tamil',
    'te-IN': 'Telugu',
    'hi-IN': 'Hindi',
    'en-IN': 'English',
    'kn-IN': 'Kannada',
    'ml-IN': 'Malayalam',
    'mr-IN': 'Marathi',
    'bn-IN': 'Bengali',
    'gu-IN': 'Gujarati',
    'pa-IN': 'Punjabi',
    auto: 'Auto-detected',
  };
  return labels[code] || code || 'Auto-detected';
}
