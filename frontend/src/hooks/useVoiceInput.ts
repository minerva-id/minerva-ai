import { useCallback, useEffect, useRef, useState } from 'react';

interface UseVoiceInputOptions {
  language?: string;
  onTranscript?: (text: string) => void;
  onPartial?: (text: string) => void;
}

export function useVoiceInput({
  language = 'id-ID',
  onTranscript,
  onPartial,
}: UseVoiceInputOptions = {}) {
  const [isListening, setIsListening] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const [partialTranscript, setPartialTranscript] = useState('');
  const recognitionRef = useRef<any>(null);
  const onTranscriptRef = useRef(onTranscript);
  const onPartialRef = useRef(onPartial);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
    onPartialRef.current = onPartial;
  }, [onTranscript, onPartial]);

  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    setIsSupported(!!SR);
  }, []);

  const startListening = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    const recognition = new SR();
    recognition.lang = language;
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: any) => {
      let interim = '';
      let final = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += transcript;
        } else {
          interim += transcript;
        }
      }

      if (interim) {
        setPartialTranscript(interim);
        onPartialRef.current?.(interim);
      }

      if (final) {
        setPartialTranscript('');
        setIsListening(false);
        onTranscriptRef.current?.(final.trim());
      }
    };

    recognition.onerror = () => {
      setIsListening(false);
      setPartialTranscript('');
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
    setPartialTranscript('');
  }, [language]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  const toggleListening = useCallback(() => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, startListening, stopListening]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
    };
  }, []);

  return {
    isListening,
    isSupported,
    partialTranscript,
    startListening,
    stopListening,
    toggleListening,
  };
}

// Type augmentation for browsers that use webkit prefix
declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}
