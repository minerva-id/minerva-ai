import { useEffect, useState } from 'react';

export default function HudHeader() {
  const [time, setTime] = useState('');

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString('en-GB', { hour12: false }));
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="hud-header">
      <div className="hud-header-left">
        <h1 className="hud-title">M I N E R V A</h1>
        <span className="hud-subtitle">TRADING INTELLIGENCE</span>
      </div>
      <div id="clock">{time}</div>
    </header>
  );
}
