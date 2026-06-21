import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';

export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  type?: 'text' | 'chart';
  isStreaming?: boolean;
}

interface ChatFeedProps {
  messages: Message[];
  partialTranscript?: string;
}

export default function ChatFeed({ messages, partialTranscript }: ChatFeedProps) {
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [messages, partialTranscript]);

  const roleClass = (role: string) => {
    if (role === 'user') return 'msg you';
    if (role === 'assistant') return 'msg jarvis';
    return 'msg sys';
  };

  return (
    <div id="feed" ref={feedRef}>
      {messages.map((msg, i) => (
        <div
          key={i}
          className={`${roleClass(msg.role)}${msg.isStreaming ? ' live' : ''}`}
        >
          {msg.role === 'assistant' ? (
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          ) : (
            msg.content
          )}
        </div>
      ))}

      {partialTranscript && (
        <div className="msg you live">
          🎤 {partialTranscript}
        </div>
      )}
    </div>
  );
}
