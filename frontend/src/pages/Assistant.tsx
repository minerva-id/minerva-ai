import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Send, Bot, User } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function Assistant() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<any[]>([{
    role: 'assistant',
    content: "Halo! Saya Minerva, asisten AI trading Anda. Ada yang bisa saya bantu analisa hari ini?",
    type: 'text'
  }]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<null | HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (e: any) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg = { role: 'user', content: input, type: 'text' };
    const history = messages.map(m => ({ role: m.role, content: m.content }));
    
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input, history })
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(prev => [...prev, data]);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: 'Maaf, terjadi kesalahan saat menghubungi server.', type: 'text' }]);
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Gagal menghubungi server.', type: 'text' }]);
    } finally {
      setLoading(false);
    }
  };

  const renderChart = (chartData: any) => {
    if (!chartData || !chartData.data) return null;
    return (
      <div style={{ width: '100%', height: 300, marginTop: '1rem', backgroundColor: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '8px' }}>
        <h4 style={{ marginBottom: '1rem', textAlign: 'center', color: 'var(--accent-cyan)' }}>{chartData.title}</h4>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData.data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey="time" stroke="#888" />
            <YAxis stroke="#888" domain={['auto', 'auto']} />
            <Tooltip contentStyle={{ backgroundColor: '#111', border: '1px solid #333' }} />
            <Line type="monotone" dataKey="price" stroke="var(--accent-cyan)" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="value" stroke="var(--accent-purple)" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  };

  return (
    <div className="animate-fade-in" style={{ height: 'calc(100vh - 4rem)', display: 'flex', flexDirection: 'column' }}>
      <header className="page-header" style={{ marginBottom: '1rem' }}>
        <div>
          <h1 className="page-title">Minerva Assistant</h1>
          <p className="page-subtitle">Your conversational trading copilot</p>
        </div>
      </header>

      <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {messages.map((msg, i) => (
            <div key={i} style={{ 
              display: 'flex', 
              gap: '1rem',
              alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: msg.role === 'user' ? '80%' : '100%'
            }}>
              {msg.role === 'assistant' && (
                <div style={{ width: 36, height: 36, borderRadius: '50%', backgroundColor: 'rgba(6, 182, 212, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Bot size={20} color="var(--accent-cyan)" />
                </div>
              )}
              
              <div style={{
                backgroundColor: msg.role === 'user' ? 'var(--accent-blue)' : 'rgba(255, 255, 255, 0.03)',
                padding: '1rem 1.25rem',
                borderRadius: '12px',
                border: msg.role === 'assistant' ? '1px solid var(--border-color)' : 'none',
                color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
                fontSize: '0.95rem',
                lineHeight: 1.6
              }}>
                <ReactMarkdown>{msg.content}</ReactMarkdown>
                {msg.type === 'chart' && renderChart(msg.chart_data)}
              </div>

              {msg.role === 'user' && (
                <div style={{ width: 36, height: 36, borderRadius: '50%', backgroundColor: 'rgba(59, 130, 246, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <User size={20} color="var(--accent-blue)" />
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div style={{ display: 'flex', gap: '1rem', alignSelf: 'flex-start' }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', backgroundColor: 'rgba(6, 182, 212, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Bot size={20} color="var(--accent-cyan)" />
              </div>
              <div style={{ padding: '1rem', color: 'var(--text-secondary)' }}>
                Minerva is thinking...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div style={{ padding: '1rem', borderTop: '1px solid var(--border-color)' }}>
          <form onSubmit={handleSend} style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              className="form-input"
              placeholder="Ask Minerva to analyze BTC/USDT or show portfolio..."
              disabled={loading}
              style={{ flex: 1 }}
            />
            <button type="submit" className="btn btn-primary" disabled={loading || !input.trim()}>
              <Send size={18} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
