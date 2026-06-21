import { useEffect, useState } from 'react';
import { Activity, Clock, ShieldCheck, Zap } from 'lucide-react';

export default function Dashboard() {
  const [health, setHealth] = useState<any>(null);

  const fetchHealth = async () => {
    try {
      const res = await fetch('/health');
      if (res.ok) {
        setHealth(await res.json());
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="animate-fade-in">
      <header className="page-header">
        <div>
          <h1 className="page-title">Dashboard Overview</h1>
          <p className="page-subtitle">Real-time status of Minerva AI trading agent</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span className={`status-dot ${health?.status === 'running' ? 'online' : ''}`}></span>
          <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>
            {health?.status === 'running' ? 'Agent Online' : 'Agent Offline'}
          </span>
        </div>
      </header>

      <div className="stats-grid animate-delay-1">
        <div className="glass-panel stat-card">
          <div className="stat-label"><Activity size={16} className="text-cyan-500" /> Bot State</div>
          <div className="stat-value">{health?.bot_state || 'Loading...'}</div>
        </div>
        <div className="glass-panel stat-card">
          <div className="stat-label"><Clock size={16} className="text-blue-500" /> Uptime (s)</div>
          <div className="stat-value">{health?.uptime_seconds || 0}</div>
        </div>
        <div className="glass-panel stat-card">
          <div className="stat-label"><Zap size={16} className="text-purple-500" /> Loop Count</div>
          <div className="stat-value">{health?.loop_count || 0}</div>
        </div>
        <div className="glass-panel stat-card">
          <div className="stat-label"><ShieldCheck size={16} className="text-green-500" /> Started At</div>
          <div className="stat-value" style={{ fontSize: '1rem', marginTop: 'auto' }}>
            {health?.started_at ? new Date(health.started_at).toLocaleString() : 'Loading...'}
          </div>
        </div>
      </div>

      <div className="glass-panel animate-delay-2" style={{ padding: '2rem' }}>
        <h2 style={{ marginBottom: '1rem', fontSize: '1.25rem', fontWeight: 600 }}>System Status</h2>
        <p style={{ color: 'var(--text-secondary)' }}>
          To view active trading positions, navigate to the <a href="/positions">Positions</a> page.
          To update API keys or agent parameters, visit <a href="/configuration">Configuration</a>.
        </p>
        
        {/* Placeholder for future charting component */}
        <div style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px dashed var(--border-color)', borderRadius: 'var(--radius-md)', marginTop: '2rem' }}>
          <span style={{ color: 'var(--text-muted)' }}>Equity Chart (Coming Soon)</span>
        </div>
      </div>
    </div>
  );
}
