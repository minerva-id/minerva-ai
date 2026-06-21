import { useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Mic, MicOff, Square } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isListening: boolean;
  toggleListening: () => void;
  agentThinking: boolean;
}

export default function ChatInput({
  onSend,
  onStop,
  isListening,
  toggleListening,
  agentThinking,
}: ChatInputProps) {
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (input.trim() && !agentThinking) {
      onSend(input.trim());
      setInput('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSend();
    }
  };

  return (
    <div id="chatRow">
      <input
        id="chatInput"
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Awaiting input... (/market, /portfolio, /analyze)"
        disabled={agentThinking}
        autoComplete="off"
      />
      
      {agentThinking ? (
        <button id="stopBtn" className="btn danger" onClick={onStop} style={{ display: 'flex' }}>
          <Square size={14} style={{ marginRight: '6px' }} />
          STOP
        </button>
      ) : (
        <>
          <button
            className={`btn ${isListening ? 'amber' : ''}`}
            onClick={toggleListening}
            title="Voice Input"
          >
            {isListening ? <MicOff size={14} /> : <Mic size={14} />}
          </button>
          <button className="btn" onClick={handleSend} disabled={!input.trim()}>
            SEND
          </button>
        </>
      )}
    </div>
  );
}
