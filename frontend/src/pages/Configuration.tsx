import { useEffect, useState } from 'react';
import { Save, AlertTriangle } from 'lucide-react';

export default function Configuration() {
  const [config, setConfig] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const fetchConfig = async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        setConfig(await res.json());
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleChange = (e: any) => {
    setConfig({ ...config, [e.target.name]: e.target.value });
  };

  const handleSave = async (e: any) => {
    e.preventDefault();
    setSaving(true);
    setMessage('');
    try {
      // Include _restart flag to tell backend to restart process
      const payload = { ...config, _restart: true };
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        setMessage('Configuration saved! Agent is restarting...');
        setTimeout(() => setMessage(''), 5000);
      }
    } catch (err) {
      setMessage('Failed to save configuration.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="animate-fade-in">
      <header className="page-header">
        <div>
          <h1 className="page-title">Configuration</h1>
          <p className="page-subtitle">Manage environment variables and agent settings</p>
        </div>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          <Save size={16} />
          {saving ? 'Saving...' : 'Save & Restart'}
        </button>
      </header>

      {message && (
        <div className="glass-panel" style={{ padding: '1rem', marginBottom: '2rem', backgroundColor: 'rgba(16, 185, 129, 0.1)', borderColor: 'var(--accent-green)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <AlertTriangle size={18} className="text-green-500" />
          <span style={{ color: 'var(--text-primary)' }}>{message}</span>
        </div>
      )}

      <div className="glass-panel animate-delay-1" style={{ padding: '2rem' }}>
        <form onSubmit={handleSave}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1.5rem', color: 'var(--accent-cyan)' }}>Core Settings</h2>
          
          <div className="stats-grid">
            <div className="form-group">
              <label className="form-label">Primary Exchange</label>
              <input type="text" name="PRIMARY_EXCHANGE" value={config['PRIMARY_EXCHANGE'] || ''} onChange={handleChange} className="form-input" />
            </div>
            <div className="form-group">
              <label className="form-label">Agent Mode</label>
              <input type="text" name="AGENT_MODE" value={config['AGENT_MODE'] || ''} onChange={handleChange} className="form-input" placeholder="paper or live" />
            </div>
          </div>
          
          <div className="form-group">
            <label className="form-label">Trading Pairs (comma separated)</label>
            <input type="text" name="TRADING_PAIRS" value={config['TRADING_PAIRS'] || ''} onChange={handleChange} className="form-input" />
          </div>

          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, margin: '2.5rem 0 1.5rem', color: 'var(--accent-purple)' }}>Risk Limits</h2>
          <div className="stats-grid">
            <div className="form-group">
              <label className="form-label">Max Position Size (USD)</label>
              <input type="number" name="MAX_POSITION_SIZE_USD" value={config['MAX_POSITION_SIZE_USD'] || ''} onChange={handleChange} className="form-input" />
            </div>
            <div className="form-group">
              <label className="form-label">Max Drawdown (%)</label>
              <input type="number" step="0.01" name="MAX_DRAWDOWN_PERCENT" value={config['MAX_DRAWDOWN_PERCENT'] || ''} onChange={handleChange} className="form-input" />
            </div>
          </div>

          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, margin: '2.5rem 0 1.5rem', color: 'var(--accent-blue)' }}>API Keys</h2>
          <div className="stats-grid">
            <div className="form-group">
              <label className="form-label">OpenAI API Key</label>
              <input type="password" name="OPENAI_API_KEY" value={config['OPENAI_API_KEY'] || ''} onChange={handleChange} className="form-input" />
            </div>
            <div className="form-group">
              <label className="form-label">Groq API Key</label>
              <input type="password" name="GROQ_API_KEY" value={config['GROQ_API_KEY'] || ''} onChange={handleChange} className="form-input" />
            </div>
            <div className="form-group">
              <label className="form-label">Binance API Key</label>
              <input type="password" name="BINANCE_API_KEY" value={config['BINANCE_API_KEY'] || ''} onChange={handleChange} className="form-input" />
            </div>
            <div className="form-group">
              <label className="form-label">Binance API Secret</label>
              <input type="password" name="BINANCE_API_SECRET" value={config['BINANCE_API_SECRET'] || ''} onChange={handleChange} className="form-input" />
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
