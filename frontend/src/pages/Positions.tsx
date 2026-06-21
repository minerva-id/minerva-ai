import { useEffect, useState } from 'react';

export default function Positions() {
  const [positions, setPositions] = useState<any>({});
  const [loading, setLoading] = useState(true);

  const fetchPositions = async () => {
    try {
      const res = await fetch('/api/positions');
      if (res.ok) {
        const data = await res.json();
        setPositions(data.positions || {});
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPositions();
    const interval = setInterval(fetchPositions, 10000);
    return () => clearInterval(interval);
  }, []);

  const positionKeys = Object.keys(positions);

  return (
    <div className="animate-fade-in">
      <header className="page-header">
        <div>
          <h1 className="page-title">Active Positions</h1>
          <p className="page-subtitle">Current open trades across all configured exchanges</p>
        </div>
      </header>

      <div className="glass-panel animate-delay-1" style={{ overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
            Loading positions...
          </div>
        ) : positionKeys.length === 0 ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
            No active positions found.
          </div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Size</th>
                  <th>Entry Price</th>
                  <th>Current Price</th>
                  <th>PnL</th>
                </tr>
              </thead>
              <tbody>
                {positionKeys.map((symbol) => {
                  const pos = positions[symbol];
                  return (
                    <tr key={symbol}>
                      <td style={{ fontWeight: 600 }}>{symbol}</td>
                      <td>
                        <span className={`badge ${pos.side === 'long' ? 'badge-success' : 'badge-error'}`}>
                          {pos.side.toUpperCase()}
                        </span>
                      </td>
                      <td>{pos.size}</td>
                      <td>${pos.entry_price?.toFixed(2)}</td>
                      <td>${pos.current_price?.toFixed(2) || 'N/A'}</td>
                      <td className={pos.unrealized_pnl >= 0 ? 'positive' : 'negative'} style={{ fontWeight: 600 }}>
                        ${pos.unrealized_pnl?.toFixed(2) || '0.00'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
