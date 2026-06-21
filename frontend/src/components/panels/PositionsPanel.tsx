interface Position {
  symbol: string;
  side: string;
  size: number;
  entry_price: number;
  current_price?: number;
  unrealized_pnl: number;
}

interface PositionsPanelProps {
  positions: Record<string, Position>;
}

export default function PositionsPanel({ positions }: PositionsPanelProps) {
  const positionList = Object.values(positions);

  return (
    <div className="panel">
      <h2>OPEN POSITIONS <span>POS.03</span></h2>
      {positionList.length === 0 ? (
        <div style={{ fontStyle: 'italic', opacity: 0.5, fontSize: '13px' }}>No active positions.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {positionList.map((pos) => (
            <div key={pos.symbol} style={{ borderBottom: '1px solid var(--line)', paddingBottom: '6px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                <span style={{ fontWeight: 600 }}>{pos.symbol}</span>
                <span style={{ color: pos.side === 'long' ? 'var(--teal)' : 'var(--red)', fontSize: '12px', fontWeight: 600 }}>
                  {pos.side.toUpperCase()}
                </span>
              </div>
              <div className="kv">
                <span>PnL</span>
                <b className={pos.unrealized_pnl >= 0 ? 'ok' : 'err'}>
                  {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                </b>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
