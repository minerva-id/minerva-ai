import type { ConnectionState } from '../hooks/useWebSocket';

interface HudFooterProps {
  wsState: ConnectionState;
  agentStatus: string;
  botState: string;
  uptime: number;
}

export default function HudFooter({ wsState, agentStatus, botState, uptime }: HudFooterProps) {
  const formatUptime = (s: number) => {
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  };

  return (
    <footer className="hud-footer">
      <div className="hud-footer-left">
        <span className="hud-footer-item">
          <span className={`dot ${botState === 'running' ? 'on' : 'off'}`} />
          MINERVA {botState === 'running' ? 'ONLINE' : 'OFFLINE'}
        </span>
        <span className="hud-footer-item">
          <span className={`dot ${wsState === 'connected' ? 'on' : 'off'}`} />
          RELAY {wsState.toUpperCase()}
        </span>
        <span className="hud-footer-item">
          <span className={`dot ${agentStatus !== 'error' ? 'on' : 'off'}`} />
          AGENT {agentStatus.toUpperCase()}
        </span>
      </div>
      <div className="hud-footer-right">
        <span>UPTIME {formatUptime(uptime)}</span>
        <span>v2.0</span>
      </div>
    </footer>
  );
}
