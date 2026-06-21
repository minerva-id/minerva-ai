import { useEffect, useState } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import type { WsMessage } from './hooks/useWebSocket';
import { useVoiceInput } from './hooks/useVoiceInput';
import { useSpeechSynthesis } from './hooks/useSpeechSynthesis';

import HudHeader from './components/HudHeader';
import HudFooter from './components/HudFooter';
import ArcReactor from './components/ArcReactor';
import ChatFeed from './components/ChatFeed';
import type { Message } from './components/ChatFeed';
import ChatInput from './components/ChatInput';
import BootSequence from './components/BootSequence';

import MinervaStatus from './components/panels/MinervaStatus';
import AgentActivity from './components/panels/AgentActivity';
import type { ActivityEvent } from './components/panels/AgentActivity';
import MarketPanel from './components/panels/MarketPanel';
import PositionsPanel from './components/panels/PositionsPanel';
import NewsPanel from './components/panels/NewsPanel';
import HoloContainer from './components/HoloContainer';

export default function App() {
  const [booting, setBooting] = useState(true);
  const [bootDone, setBootDone] = useState(false);

  // Core State
  const [messages, setMessages] = useState<Message[]>([]);
  const [agentThinking, setAgentThinking] = useState(false);
  
  // Panel State
  const [minervaStatus, setMinervaStatus] = useState<any>({ bot_running: false });
  const [activities, setActivities] = useState<ActivityEvent[]>([]);
  const [markets, setMarkets] = useState<any>({});
  const [positions, setPositions] = useState<any>({});
  const [news] = useState<any[]>([]);

  const tts = useSpeechSynthesis();

  // Handle WebSocket events
  const handleWsMessage = (msg: WsMessage) => {
    switch (msg.type) {
      case 'status':
        if (msg.state === 'connected') {
          // Send initial subscribe
          sendMessage('subscribe', { channels: ['market', 'trades', 'alerts'] });
        }
        break;

      case 'agent_status':
        setAgentThinking(msg.state === 'thinking' || msg.state === 'tool_use');
        break;

      case 'chat_response':
        const data = msg.data as any;
        setMessages(prev => [...prev, {
          role: data.role || 'assistant',
          content: data.content,
          type: data.type || 'text',
        }]);
        if (msg.audio) {
          const audio = new Audio("data:audio/mpeg;base64," + msg.audio);
          audio.play().catch(e => console.error("Audio block", e));
        } else if (data.content) {
          tts.speak(data.content);
        }
        break;

      case 'tool_event':
        setActivities(prev => [...prev, {
          id: Math.random().toString(),
          tool: String(msg.tool),
          status: String(msg.status),
          timestamp: String(msg.timestamp || new Date().toISOString()),
        }].slice(-20)); // Keep last 20
        break;

      case 'market_update':
        if (msg.alert_type === 'market_update') {
          const marketData = msg.data as any;
          setMarkets((prev: any) => ({
            ...prev,
            [marketData.symbol]: marketData
          }));
        }
        break;
        
      case 'trade_alert':
        // Handle trade updates
        break;

      case 'error':
        setMessages(prev => [...prev, {
          role: 'system',
          content: String(msg.message),
        }]);
        break;
    }
  };

  const wsUrl = `ws://${window.location.hostname}:8081/ws`;
  const { state: wsState, sendMessage } = useWebSocket({
    url: wsUrl,
    onMessage: handleWsMessage,
  });

  // Handle Voice Input
  const handleVoiceAudio = (base64Audio: string) => {
    sendMessage('voice_audio', { audio: base64Audio });
  };

  const { isListening, partialTranscript, toggleListening } = useVoiceInput({
    onAudio: handleVoiceAudio,
  });

  // Actions
  const handleSendMessage = (text: string) => {
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    sendMessage('chat', { message: text });
  };

  const handleStopRun = () => {
    sendMessage('stop_run');
    tts.stop();
  };

  const toggleBotStatus = async () => {
    try {
      const action = minervaStatus.bot_running ? 'stop' : 'start';
      const res = await fetch(`/api/bot/${action}`, { method: 'POST' });
      if (res.ok) {
        fetchStatus();
      }
    } catch (e) {
      console.error('Failed to toggle bot', e);
    }
  };

  // Poll HTTP status (since health/positions aren't fully pushed yet)
  const fetchStatus = async () => {
    try {
      const res = await fetch('/health');
      if (res.ok) setMinervaStatus(await res.json());
    } catch (e) {}
  };

  const fetchPositions = async () => {
    try {
      const res = await fetch('/api/positions');
      if (res.ok) {
        const data = await res.json();
        setPositions(data.positions || {});
      }
    } catch (e) {}
  };

  useEffect(() => {
    fetchStatus();
    fetchPositions();
    const interval = setInterval(() => {
      fetchStatus();
      fetchPositions();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // Update body class for boot animations
  useEffect(() => {
    document.body.className = booting ? 'booting' : 'booted';
  }, [booting]);

  const getReactorState = () => {
    if (isListening) return 'listening';
    if (agentThinking) return 'thinking';
    if (tts.isSpeaking) return 'speaking';
    return 'ready';
  };

  return (
    <>
      {(!bootDone) && (
        <BootSequence 
          onComplete={() => {
            setBooting(false);
            setTimeout(() => setBootDone(true), 700);
          }} 
        />
      )}

      <div id="grid">
        <HudHeader />

        {/* Left Column */}
        <div className="col">
          <HoloContainer>
            <MinervaStatus status={minervaStatus} onToggleBot={toggleBotStatus} />
          </HoloContainer>
          <HoloContainer>
            <PositionsPanel positions={positions} />
          </HoloContainer>
        </div>

        {/* Center Column */}
        <div id="center">
          <ArcReactor 
            state={getReactorState()} 
            onClick={toggleListening} 
          />
          <ChatFeed 
            messages={messages} 
            partialTranscript={partialTranscript} 
          />
          <ChatInput 
            onSend={handleSendMessage}
            onStop={handleStopRun}
            isListening={isListening}
            toggleListening={toggleListening}
            agentThinking={agentThinking}
          />
        </div>

        {/* Right Column */}
        <div className="col">
          <HoloContainer>
            <AgentActivity events={activities} />
          </HoloContainer>
          <HoloContainer>
            <MarketPanel markets={markets} />
          </HoloContainer>
          <HoloContainer>
            <NewsPanel news={news} />
          </HoloContainer>
        </div>

        <HudFooter 
          wsState={wsState} 
          agentStatus={agentThinking ? 'thinking' : 'idle'} 
          botState={minervaStatus.bot_running ? 'running' : 'stopped'}
          uptime={minervaStatus.uptime || 0}
        />
      </div>
    </>
  );
}
