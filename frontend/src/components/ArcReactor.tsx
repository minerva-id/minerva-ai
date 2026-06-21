interface ArcReactorProps {
  state: 'ready' | 'listening' | 'thinking' | 'speaking';
  onClick: () => void;
}

export default function ArcReactor({ state, onClick }: ArcReactorProps) {
  const stateLabels: Record<string, string> = {
    ready: 'READY',
    listening: 'LISTENING',
    thinking: 'THINKING',
    speaking: 'SPEAKING',
  };

  const stateHints: Record<string, string> = {
    ready: 'CLICK TO SPEAK',
    listening: 'SPEAK NOW',
    thinking: 'PROCESSING',
    speaking: 'RESPONDING',
  };

  return (
    <div
      id="reactorWrap"
      className={`reactor-state-${state}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`Voice input: ${stateLabels[state]}`}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
    >
      <svg id="reactor" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
        {/* Outer ring */}
        <circle cx="200" cy="200" r="185" fill="none" stroke="var(--line)" strokeWidth="1" opacity="0.5" />
        <circle cx="200" cy="200" r="175" fill="none" stroke="var(--cyan-dim)" strokeWidth="0.5" strokeDasharray="4 8" className="reactor-ring-outer" />

        {/* Mid rings */}
        <circle cx="200" cy="200" r="150" fill="none" stroke="var(--line)" strokeWidth="1" />
        <circle cx="200" cy="200" r="140" fill="none" stroke="var(--cyan)" strokeWidth="1.5" opacity="0.3" className="reactor-ring-mid" />

        {/* Tick marks */}
        {Array.from({ length: 36 }).map((_, i) => {
          const angle = (i * 10) * Math.PI / 180;
          const r1 = 152;
          const r2 = i % 3 === 0 ? 168 : 160;
          return (
            <line
              key={i}
              x1={200 + r1 * Math.cos(angle)}
              y1={200 + r1 * Math.sin(angle)}
              x2={200 + r2 * Math.cos(angle)}
              y2={200 + r2 * Math.sin(angle)}
              stroke={i % 3 === 0 ? 'var(--cyan)' : 'var(--line)'}
              strokeWidth={i % 3 === 0 ? 1.5 : 0.8}
              opacity={i % 3 === 0 ? 0.7 : 0.3}
            />
          );
        })}

        {/* Inner ring */}
        <circle cx="200" cy="200" r="105" fill="none" stroke="var(--cyan-dim)" strokeWidth="1.5" className="reactor-ring-inner" />

        {/* Core glow */}
        <defs>
          <radialGradient id="coreGlow">
            <stop offset="0%" stopColor="var(--cyan)" stopOpacity="0.4" />
            <stop offset="40%" stopColor="var(--cyan)" stopOpacity="0.15" />
            <stop offset="100%" stopColor="var(--cyan)" stopOpacity="0" />
          </radialGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <circle cx="200" cy="200" r="100" fill="url(#coreGlow)" className="reactor-core" />

        {/* Inner triangle pattern */}
        <polygon
          points="200,130 260,230 140,230"
          fill="none"
          stroke="var(--cyan)"
          strokeWidth="1"
          opacity="0.25"
          className="reactor-tri"
        />

        {/* Center dot */}
        <circle cx="200" cy="200" r="8" fill="var(--cyan)" filter="url(#glow)" opacity="0.9" className="reactor-center" />
      </svg>

      <div id="coreState">
        <div className="st">{stateLabels[state]}</div>
        <div className="hint">{stateHints[state]}</div>
      </div>
    </div>
  );
}
