import { useEffect, useRef } from 'react';

export interface ActivityEvent {
  id: string;
  tool: string;
  status: string;
  timestamp: string;
}

interface AgentActivityProps {
  events: ActivityEvent[];
}

export default function AgentActivity({ events }: AgentActivityProps) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [events]);

  return (
    <div className="panel">
      <h2>ACTIVITY STREAM <span>ACT.01</span></h2>
      <div id="activity" ref={listRef}>
        {events.length === 0 ? (
          <div style={{ fontStyle: 'italic', opacity: 0.5 }}>No recent activity...</div>
        ) : (
          events.map((ev) => (
            <div key={ev.id}>
              <span style={{ color: 'var(--txt-dim)', marginRight: '6px' }}>
                {new Date(ev.timestamp).toLocaleTimeString([], { hour12: false })}
              </span>
              ▸ <b>{ev.tool}</b> <span style={{ opacity: 0.7 }}>[{ev.status}]</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
