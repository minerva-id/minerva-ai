interface NewsItem {
  id: number;
  title: string;
  source: string;
  published_at: string;
  url: string;
}

interface NewsPanelProps {
  news: NewsItem[];
}

export default function NewsPanel({ news }: NewsPanelProps) {
  return (
    <div className="panel">
      <h2>LATEST NEWS <span>NWS.04</span></h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {news.length === 0 ? (
          <div style={{ fontStyle: 'italic', opacity: 0.5, fontSize: '13px' }}>No recent news.</div>
        ) : (
          news.slice(0, 5).map((item) => (
            <div key={item.id} style={{ fontSize: '12px' }}>
              <div style={{ color: 'var(--txt-dim)', fontSize: '10px', marginBottom: '2px' }}>
                {item.source} • {new Date(item.published_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
              <a 
                href={item.url} 
                target="_blank" 
                rel="noreferrer" 
                style={{ color: 'var(--txt)', textDecoration: 'none', lineHeight: 1.3 }}
              >
                {item.title}
              </a>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
