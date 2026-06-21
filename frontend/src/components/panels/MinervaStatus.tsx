interface MinervaStatusProps {
  status: {
    agent_mode: string;
    bot_running: boolean;
    uptime: number;
    loop_count: number;
    health: {
      redis: string;
      exchange: string;
      mcp: string;
    };
  };
  onToggleBot: () => void;
}

export default function MinervaStatus({ status, onToggleBot }: MinervaStatusProps) {
  const formatUptime = (s: number) => {
    if (!s) return '0s';
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  };

  return (
    <div className="panel">
      <h2>AGENT CORE <span>SYS.01</span></h2>
      <div className="kv">
        <span>MODE</span>
        <b>{status.agent_mode?.toUpperCase() || 'UNKNOWN'}</b>
      </div>
      <div className="kv">
        <span>STATUS</span>
        <b className={status.bot_running ? 'ok' : 'warn'}>
          {status.bot_running ? 'ONLINE' : 'STANDBY'}
        </b>
      </div>
      <div className="kv">
        <span>UPTIME</span>
        <b>{formatUptime(status.uptime)}</b>
      </div>
      <div className="kv">
        <span>LOOPS</span>
        <b>{status.loop_count || 0}</b>
      </div>

      <h2 style={{ marginTop: '12px' }}>SUBSYSTEMS</h2>
      <div className="kv">
        <span>REDIS MEMORY</span>
        <span className={status.health?.redis === 'ok' ? 'ok' : 'err'}>
          <span className={`dot ${status.health?.redis === 'ok' ? 'on' : 'off'}`} />
          {status.health?.redis?.toUpperCase() || 'ERR'}
        </span>
      </div>
      <div className="kv">
        <span>EXCHANGE API</span>
        <span className={status.health?.exchange === 'ok' ? 'ok' : 'err'}>
          <span className={`dot ${status.health?.exchange === 'ok' ? 'on' : 'off'}`} />
          {status.health?.exchange?.toUpperCase() || 'ERR'}
        </span>
      </div>
      <div className="kv">
        <span>MCP BRIDGE</span>
        <span className={status.health?.mcp === 'ok' ? 'ok' : 'err'}>
          <span className={`dot ${status.health?.mcp === 'ok' ? 'on' : 'off'}`} />
          {status.health?.mcp?.toUpperCase() || 'ERR'}
        </span>
      </div>

      <button
        className={`btn ${status.bot_running ? 'amber' : ''}`}
        style={{ width: '100%', marginTop: '12px' }}
        onClick={onToggleBot}
      >
        {status.bot_running ? 'HALT AGENT' : 'START AGENT'}
      </button>
    </div>
  );
}
