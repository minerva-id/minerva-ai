interface MarketData {
  symbol: string;
  price: number;
  change_24h: number;
}

interface MarketPanelProps {
  markets: Record<string, MarketData>;
}

export default function MarketPanel({ markets }: MarketPanelProps) {
  const pairs = Object.values(markets);

  return (
    <div className="panel">
      <h2>MARKET DATA <span>MKT.02</span></h2>
      {pairs.length === 0 ? (
        <div style={{ fontStyle: 'italic', opacity: 0.5, fontSize: '13px' }}>Waiting for market data...</div>
      ) : (
        pairs.map((m) => (
          <div key={m.symbol} className="kv" style={{ padding: '4px 0' }}>
            <span style={{ fontWeight: 600 }}>{m.symbol}</span>
            <div style={{ textAlign: 'right' }}>
              <div>${m.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}</div>
              <div className={m.change_24h >= 0 ? 'ok' : 'err'} style={{ fontSize: '11px' }}>
                {m.change_24h >= 0 ? '+' : ''}{m.change_24h.toFixed(2)}%
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
