import { useState, useEffect, useRef } from 'react';
import { 
  Terminal, Activity, Compass, Search, Users, 
  Radio, Layers, Settings, Copy, Check, 
  AlertTriangle, Volume2, VolumeX, Eye
} from 'lucide-react';
import './App.css';

// Types
interface Wallet {
  address: string;
  name: string;
  type: 'KOL' | 'Smart Wallet' | 'Ave' | 'Callout';
  profit: number;
  wins: number;
  losses: number;
  winrate: number;
}

interface Transaction {
  signature: string;
  walletName: string;
  walletAddress: string;
  action: 'BUY' | 'SELL';
  tokenName: string;
  tokenSymbol: string;
  tokenAddress: string;
  amountSol: number;
  amountTokens: number;
  usdValue: number;
  marketCap: string;
  ageDays: number;
  whales: number;
  dolphins: number;
  shrimps: number;
  platform: string;
  timestamp: string;
}

// Initial Mock Wallets
const INITIAL_WALLETS: Wallet[] = [
  { address: "3e48pUwNFa38agfZ8iEtnahWKAPixcfspump", name: "Smart Wallet 3e48 (Callout)", type: "Smart Wallet", profit: 124.5, wins: 45, losses: 12, winrate: 78.9 },
  { address: "GJvYTShXcya7ZqJ2jFL4MBnvdqrwedgmaaxKHJUFb2f1", name: "Smart Wallet GJvY (Callout)", type: "Smart Wallet", profit: 89.2, wins: 38, losses: 15, winrate: 71.6 },
  { address: "Dv32u9mvSXGVNshf7xM7afuMoPRifQxzuzEjfmfMysZY", name: "deecayz ⌐◨-◨", type: "KOL", profit: 245.8, wins: 89, losses: 31, winrate: 74.1 },
  { address: "sAdNbe1cKNMDqDsa4npB3TfL62T14uAo2MsUQfLvzLT", name: "Ethan Prosper", type: "KOL", profit: -12.4, wins: 14, losses: 20, winrate: 41.1 },
  { address: "99xnE2zEFi8YhmKDaikc1EvH6ELTQJppnqUwMzmpLXrs", name: "Coler", type: "KOL", profit: 56.7, wins: 22, losses: 10, winrate: 68.75 },
  { address: "DU323DieHUGPmYamp6A4Ai1V4YSYgRi35mGpzJGrjf7k", name: "Toxic West", type: "Ave", profit: 310.2, wins: 124, losses: 42, winrate: 74.7 },
  { address: "6AkXDj5Aq4WpGmT8Wy6WSfR1iexEZv5fQrhkkVC1kkdc", name: "Smart Wallet 6AkX (Callout)", type: "Smart Wallet", profit: 42.1, wins: 19, losses: 8, winrate: 70.3 },
  { address: "8b7R5PEqEHKsvE87XtVfdN5HP6s3JX5MGYL5KsSH3Sx9", name: "Smart Wallet 8b7R (Callout)", type: "Smart Wallet", profit: 12.8, wins: 7, losses: 4, winrate: 63.6 }
];

// Initial Mock Transactions
const INITIAL_TRANSACTIONS: Transaction[] = [
  {
    signature: "4pzqzfCKAHKc7BFyzseRYUSDfrH2SuJuaLWGXqQu2bBPgkvN7JNUSuZwWGscSBSiLHTZYXM91fksLnw1BW72Z9bi",
    walletName: "deecayz ⌐◨-◨",
    walletAddress: "Dv32u9mvSXGVNshf7xM7afuMoPRifQxzuzEjfmfMysZY",
    action: "BUY",
    tokenName: "I choose rich everytime",
    tokenSymbol: "RICH",
    tokenAddress: "5hiLgyybrAYPpUwNFa38agfZ8iEtnahWKAPixcfspump",
    amountSol: 2.5,
    amountTokens: 420512.23,
    usdValue: 425.60,
    marketCap: "$1.38M",
    ageDays: 12.4,
    whales: 20,
    dolphins: 14,
    shrimps: 10202,
    platform: "Pump.fun",
    timestamp: new Date().toLocaleTimeString()
  },
  {
    signature: "554byReMroNjBchxxLwEKYgrE2pmgo7URhCp9xUHFvPUgvwLrhLPnhrTFkAFbBJ6J65nm6XJTt8esAwVaugFKdeA",
    walletName: "Smart Wallet GJvY (Callout)",
    walletAddress: "GJvYTShXcya7ZqJ2jFL4MBnvdqrwedgmaaxKHJUFb2f1",
    action: "SELL",
    tokenName: "Giga Chad SOL Token",
    tokenSymbol: "CHAD",
    tokenAddress: "2EyVFF3U6DftMWp71exoXAWmSrBhTcT5tLgisghw78qa",
    amountSol: 3.9930,
    amountTokens: 452192.40,
    usdValue: 572.10,
    marketCap: "$2.63M",
    ageDays: 14.8,
    whales: 24,
    dolphins: 8,
    shrimps: 8431,
    platform: "Raydium",
    timestamp: new Date(Date.now() - 45000).toLocaleTimeString()
  }
];

const MOCK_TOKEN_NAMES = [
  { name: "Alpha Sentinel", symbol: "SENTINEL", address: "sent98FGsdaYtWq12gsaHsajfK12sadsfghsajk123" },
  { name: "Nebula Core", symbol: "CORE", address: "core1238asdhjasGHDAsa123asdsFasHJAasf124a" },
  { name: "Apex Protocol", symbol: "APEX", address: "apex98124HJasfKjasfiuqwh124asf124fasJHFas" },
  { name: "Titan Engine", symbol: "TITAN", address: "tita8124124ashjasFasHJAsa124asdasfghasjk" }
];

function App() {
  const wallets = INITIAL_WALLETS;
  const [transactions, setTransactions] = useState<Transaction[]>(INITIAL_TRANSACTIONS);
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(INITIAL_TRANSACTIONS[0]);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<string>('ALL');
  
  // HUD UI Customization
  const [audioEnabled, setAudioEnabled] = useState(false);
  const isOnline = true;
  const [copiedAddress, setCopiedAddress] = useState<string | null>(null);
  
  // Real-time API config
  const [apiUrl, setApiUrl] = useState('');
  const [showConfig, setShowConfig] = useState(false);
  const [apiConnected, setApiConnected] = useState(false);

  // Radar Animation Plotting Ref
  const radarCanvasRef = useRef<SVGSVGElement>(null);
  const [radarTargets, setRadarTargets] = useState<{ x: number; y: number; text: string; size: number; action: string }[]>([
    { x: 100, y: 140, text: "deecayz (RICH)", size: 8, action: "BUY" },
    { x: 220, y: 80, text: "GJvY (CHAD)", size: 10, action: "SELL" },
    { x: 150, y: 220, text: "Coler (TITAN)", size: 6, action: "BUY" }
  ]);

  // Audio effects
  const playSound = (freq: number, type: OscillatorType = 'sine', duration = 0.1) => {
    if (!audioEnabled) return;
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.05, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.00001, ctx.currentTime + duration);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + duration);
    } catch (e) {
      console.warn("Audio Context blocked", e);
    }
  };

  // Copy helper
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedAddress(text);
    playSound(880, 'sine', 0.15);
    setTimeout(() => setCopiedAddress(null), 2000);
  };

  // Simulator to mimic live transactions in dashboard
  useEffect(() => {
    if (apiConnected) return; // disable simulator if real websocket connected

    const interval = setInterval(() => {
      // 10% chance to trigger a new trade alert
      if (Math.random() > 0.6) {
        playSound(660, 'triangle', 0.25);
        
        // Random swap setup
        const sourceWallet = wallets[Math.floor(Math.random() * wallets.length)];
        const token = MOCK_TOKEN_NAMES[Math.floor(Math.random() * MOCK_TOKEN_NAMES.length)];
        const action = Math.random() > 0.5 ? 'BUY' : 'SELL';
        const solVal = Math.random() * 4.5 + 0.1;
        const pricePerToken = 0.0012 + Math.random() * 0.002;
        const tokensAmount = solVal / pricePerToken * 100;
        const usdVal = solVal * 170.0; // Assume 1 SOL = $170
        const age = 7.1 + Math.random() * 30.0;
        
        const newTx: Transaction = {
          signature: Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15),
          walletName: sourceWallet.name,
          walletAddress: sourceWallet.address,
          action,
          tokenName: token.name,
          tokenSymbol: token.symbol,
          tokenAddress: token.address,
          amountSol: solVal,
          amountTokens: tokensAmount,
          usdValue: usdVal,
          marketCap: `$${(2.1 + Math.random() * 20.0).toFixed(2)}M`,
          ageDays: age,
          whales: Math.floor(Math.random() * 15 + 5),
          dolphins: Math.floor(Math.random() * 30 + 10),
          shrimps: Math.floor(Math.random() * 8000 + 1000),
          platform: Math.random() > 0.6 ? 'Raydium' : 'Pump.fun',
          timestamp: new Date().toLocaleTimeString()
        };

        setTransactions(prev => [newTx, ...prev.slice(0, 19)]);
        setSelectedTx(newTx);

        // Update radar targets
        const rx = 50 + Math.random() * 200;
        const ry = 50 + Math.random() * 200;
        setRadarTargets(prev => [
          { x: rx, y: ry, text: `${sourceWallet.name.substring(0, 8)} (${token.symbol})`, size: 8 + Math.random() * 4, action },
          ...prev.slice(0, 4)
        ]);
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [wallets, apiConnected, audioEnabled]);

  // Handle Search & Filter
  const filteredWallets = wallets.filter(w => {
    const matchesSearch = w.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          w.address.toLowerCase().includes(searchQuery.toLowerCase());
    
    if (filterType === 'ALL') return matchesSearch;
    if (filterType === 'KOL') return matchesSearch && w.type === 'KOL';
    if (filterType === 'SMART') return matchesSearch && w.type === 'Smart Wallet';
    if (filterType === 'AVE') return matchesSearch && w.type === 'Ave';
    return matchesSearch;
  });

  return (
    <div className="min-h-vh flex flex-col font-sans relative p-3">
      {/* Background grids */}
      <div className="hud-grid"></div>
      <div className="scanline"></div>

      {/* TOP HEADER */}
      <header className="hologram-card p-3 mb-3 flex flex-wrap justify-between items-center relative overflow-hidden">
        <div className="corner-decor-tr"></div>
        <div className="corner-decor-bl"></div>

        <div className="flex items-center space-x-3">
          <div className="relative">
            <div className="w-8 h-8 rounded-full border-2 border-cyan-400 flex items-center justify-center animate-pulse">
              <Activity className="w-5 h-5 text-cyan-400" />
            </div>
            <div className="absolute top-0 right-0 w-2-5 h-2-5 bg-green-500 rounded-full border-2 border-black blink"></div>
          </div>
          <div>
            <h1 className="text-xl font-black text-cyan-400 tracking-wider font-title neon-text-cyan flex items-center">
              MINERVA J.A.R.V.I.S. HUD
              <span className="text-xs font-mono ml-3 text-cyan-500 border border-cyan-800 px-1 bg-cyan-950-10">V2.4.9</span>
            </h1>
            <p className="text-xs font-mono text-cyan-500">Solana Smart & KOL Watchtower Subsystem</p>
          </div>
        </div>

        {/* HUD System Information */}
        <div className="flex items-center space-x-6 text-right font-mono text-xs text-cyan-400 mt-2">
          <div className="sm-block border-l border-cyan-800 pl-3">
            <span className="block text-cyan-600">ACTIVE RADAR</span>
            <span className="neon-text-cyan font-bold">120 NM RANGE</span>
          </div>
          <div className="sm-block border-l border-cyan-800 pl-3">
            <span className="block text-cyan-600">TRACKED TARGETS</span>
            <span className="neon-text-cyan font-bold">{wallets.length} NODES</span>
          </div>
          <div className="border-l border-cyan-800 pl-3 flex flex-col items-end">
            <span className="block text-cyan-600">SYSTEM NET STATUS</span>
            <span className="flex items-center gap-1 font-bold text-green-400">
              <span className="w-2 h-2 rounded-full bg-green-400 inline-block blink"></span>
              {isOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>

          {/* Sound Control & API Settings */}
          <div className="flex items-center gap-2 border-l border-cyan-800 pl-3">
            <button 
              onClick={() => {
                setAudioEnabled(!audioEnabled);
                // Trigger sound check
                if(!audioEnabled) setTimeout(() => playSound(440, 'sine', 0.1), 50);
              }}
              className={`p-2 border rounded ${audioEnabled ? 'border-cyan-400 bg-cyan-950-30 text-cyan-400' : 'border-cyan-800 text-cyan-700'} hover-border-cyan-400 transition-colors`}
              title="Toggle Audio Feedback"
            >
              {audioEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            </button>
            <button 
              onClick={() => {
                setShowConfig(!showConfig);
                playSound(550, 'sine', 0.08);
              }}
              className={`p-2 border rounded ${showConfig ? 'border-orange-400 bg-orange-950-30 text-orange-400' : 'border-cyan-800 text-cyan-500'} hover-border-cyan-400 transition-colors`}
              title="API Connection Panel"
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* API Configuration Panel */}
      {showConfig && (
        <section className="hologram-card p-3 mb-3 border border-orange-500-50 bg-orange-950-10 text-orange-400 relative">
          <div className="corner-decor-tr" style={{ borderColor: 'var(--neon-orange)' }}></div>
          <div className="corner-decor-bl" style={{ borderColor: 'var(--neon-orange)' }}></div>
          <h3 className="font-title text-sm font-bold flex items-center gap-2 mb-2 neon-text-orange">
            <Settings className="w-4 h-4" /> API CONNECTOR SYSTEM
          </h3>
          <div className="flex flex-col sm-block gap-2 items-center">
            <div className="flex-1 w-full relative">
              <input 
                type="text" 
                placeholder="Enter API Endpoint (e.g. http://127.0.0.1:8080 or ws://...)" 
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                className="w-full bg-black-50 border border-orange-800 rounded p-2 text-xs font-mono text-orange-400 focus-outline-none focus-border-orange-400"
              />
            </div>
            <button 
              onClick={() => {
                setApiConnected(true);
                playSound(880, 'sine', 0.2);
                setShowConfig(false);
              }}
              className="w-full sm-w-auto bg-orange-950-40 border border-orange-500 px-4 py-2 text-xs font-mono text-orange-400 rounded hover-bg-cyan-950-30 transition-colors"
            >
              INITIALIZE CONNECTION
            </button>
          </div>
        </section>
      )}

      {/* DASHBOARD CONTENT GRID */}
      <div className="grid grid-cols-1 lg-grid-cols-12 gap-3 flex-1">
        
        {/* PANEL LEFT: WALLETS LIST (col-span-3) */}
        <section className="lg-col-span-3 hologram-card p-3 flex flex-col h-300px lg-h-calc-100vh-140px min-h-300px">
          <div className="corner-decor-tr"></div>
          <div className="corner-decor-bl"></div>

          {/* Panel Header */}
          <div className="flex justify-between mb-3">
            <h2 className="text-sm font-bold font-title tracking-wider neon-text-cyan flex items-center gap-2">
              <Users className="w-4 h-4" /> TARGET WATCHLIST
            </h2>
            <span className="text-10px font-mono text-cyan-500 bg-cyan-950-30 px-1 border border-cyan-800">
              {filteredWallets.length}/{wallets.length} ACTIVE
            </span>
          </div>

          {/* Search bar */}
          <div className="relative mb-2">
            <Search className="absolute left-2.5 top-2.5 w-3-5 h-3-5 text-cyan-600" style={{ pointerEvents: 'none' }} />
            <input 
              type="text" 
              placeholder="Query wallet..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-cyan-950-20 border border-cyan-900 rounded pl-8 pr-3 py-2 text-xs font-mono text-cyan-400 focus-outline-none focus-border-cyan-400 placeholder:text-cyan-850"
            />
          </div>

          {/* Type filters */}
          <div className="flex gap-1 mb-2 font-mono text-9px">
            {['ALL', 'KOL', 'SMART'].map(t => (
              <button
                key={t}
                onClick={() => {
                  setFilterType(t);
                  playSound(700, 'sine', 0.05);
                }}
                className={`flex-1 py-1 text-center border rounded ${filterType === t ? 'border-cyan-400 bg-cyan-950-30 text-cyan-400 shadow-[0_0_8px_rgba(0,240,255,0.2)]' : 'border-cyan-950 text-cyan-600 bg-transparent'} hover-border-cyan-700`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Wallet list */}
          <div className="flex-1 overflow-y-auto space-y-1-5 pr-1 font-mono text-xs">
            {filteredWallets.map(w => (
              <div 
                key={w.address} 
                className="p-2 border border-cyan-950-60 bg-cyan-950-5 rounded hover-border-cyan-800-80 hover-bg-cyan-950-30 transition-all cursor-pointer relative group"
                onClick={() => {
                  playSound(600, 'sine', 0.08);
                  // Find or simulate a transaction for this wallet to highlight details
                  const tx = transactions.find(t => t.walletAddress === w.address);
                  if (tx) {
                    setSelectedTx(tx);
                  } else {
                    // Simulate custom preview
                    setSelectedTx({
                      signature: "SAMPLE_SIG_FOR_PREVIEW_" + w.address.substring(0, 6),
                      walletName: w.name,
                      walletAddress: w.address,
                      action: "BUY",
                      tokenName: "Preview Sample Token",
                      tokenSymbol: "SAMPLE",
                      tokenAddress: "5hiLgyybrAYPpUwNFa38agfZ8iEtnahWKAPixcfspump",
                      amountSol: 1.0,
                      amountTokens: 10000.0,
                      usdValue: 170.0,
                      marketCap: "$1.5M",
                      ageDays: 14.5,
                      whales: 15,
                      dolphins: 12,
                      shrimps: 4500,
                      platform: "Raydium",
                      timestamp: "JUST NOW"
                    });
                  }
                }}
              >
                {/* Status indicator glow */}
                <div className={`absolute top-2 right-2 w-1-5 h-1-5 rounded-full ${w.profit >= 0 ? 'bg-green-400 animate-pulse' : 'bg-red-500'}`}></div>
                
                <div className="font-bold text-cyan-400 group-hover:text-cyan-300 truncate pr-4">{w.name}</div>
                <div className="text-10px text-cyan-600 truncate mb-1">`{w.address.substring(0, 16)}...`</div>
                
                <div className="flex justify-between text-10px border-t border-cyan-950-40 pt-1 mt-1 text-cyan-500">
                  <span>WINRATE: <span className="text-cyan-400 font-bold">{w.winrate}%</span></span>
                  <span className={w.profit >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {w.profit >= 0 ? `+${w.profit}` : w.profit} SOL
                  </span>
                </div>
              </div>
            ))}
            {filteredWallets.length === 0 && (
              <div className="text-center text-cyan-800 py-8">NO MATCHED DATA</div>
            )}
          </div>
        </section>

        {/* PANEL CENTER: RADAR & LIVE FEED (col-span-5) */}
        <section className="lg-col-span-5 flex flex-col gap-3 h-300px lg-h-calc-100vh-140px min-h-500px">
          
          {/* TOP PART: RADAR SCANNER HUD */}
          <div className="hologram-card p-3 flex-1 flex flex-col justify-between relative overflow-hidden">
            <div className="corner-decor-tr"></div>
            <div className="corner-decor-bl"></div>

            <div className="flex justify-between items-center mb-2">
              <h2 className="text-sm font-bold font-title tracking-wider neon-text-cyan flex items-center gap-2">
                <Compass className="w-4 h-4 animate-spin" style={{ animationDuration: '6s' }} /> RADAR TELEMETRY
              </h2>
              <span className="text-10px font-mono text-cyan-500 bg-cyan-950-30 px-1 border border-cyan-800 blink">
                SCANNING ACTIVE
              </span>
            </div>

            {/* Radar Display Container */}
            <div className="flex-1 flex items-center justify-center relative py-4">
              <svg 
                ref={radarCanvasRef}
                viewBox="0 0 300 300" 
                className="w-full max-w-[260px] aspect-square text-cyan-400"
              >
                {/* Radar Grid Circles */}
                <circle cx="150" cy="150" r="140" fill="none" stroke="currentColor" strokeWidth="0.5" strokeDasharray="3 3" opacity="0.4" />
                <circle cx="150" cy="150" r="110" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.3" />
                <circle cx="150" cy="150" r="80" fill="none" stroke="currentColor" strokeWidth="0.5" strokeDasharray="3 3" opacity="0.4" />
                <circle cx="150" cy="150" r="50" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.3" />
                <circle cx="150" cy="150" r="20" fill="none" stroke="currentColor" strokeWidth="0.5" opacity="0.5" />

                {/* Radar Crosshairs */}
                <line x1="150" y1="5" x2="150" y2="295" stroke="currentColor" strokeWidth="0.5" opacity="0.3" />
                <line x1="5" y1="150" x2="295" y2="150" stroke="currentColor" strokeWidth="0.5" opacity="0.3" />
                
                {/* Scanning Sweep Sweep */}
                <path 
                  d="M150,150 L150,10 A140,140 0 0,1 248.9,248.9 Z" 
                  fill="url(#radar-sweep-gradient)" 
                  className="radar-sweep-line"
                />

                {/* Gradients */}
                <defs>
                  <linearGradient id="radar-sweep-gradient" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="var(--neon-cyan)" stopOpacity="0.4" />
                    <stop offset="100%" stopColor="var(--neon-cyan)" stopOpacity="0" />
                  </linearGradient>
                </defs>

                {/* Plotted Targets */}
                {radarTargets.map((t, idx) => (
                  <g key={idx} className="cursor-pointer" onClick={() => playSound(770, 'sine', 0.1)}>
                    {/* Ring indicator */}
                    <circle 
                      cx={t.x} 
                      cy={t.y} 
                      r={t.size + 4} 
                      fill="none" 
                      stroke={t.action === 'BUY' ? 'var(--neon-cyan)' : 'var(--neon-orange)'} 
                      strokeWidth="1"
                      className="animate-ping" 
                      style={{ animationDuration: '2s' }}
                    />
                    {/* Core plot */}
                    <circle 
                      cx={t.x} 
                      cy={t.y} 
                      r={t.size / 2} 
                      fill={t.action === 'BUY' ? 'var(--neon-cyan)' : 'var(--neon-orange)'} 
                    />
                    {/* Label */}
                    <text 
                      x={t.x + 8} 
                      y={t.y + 3} 
                      fill="currentColor" 
                      fontSize="8" 
                      fontFamily="var(--font-hud)"
                      opacity="0.8"
                    >
                      {t.text}
                    </text>
                  </g>
                ))}
              </svg>
            </div>

            <div className="flex justify-between font-mono text-9px text-cyan-600 border-t border-cyan-950-40 pt-2">
              <span>AZ: 341.2°</span>
              <span>ELEV: +14.5°</span>
              <span>SCAN CODE: SEC_HUD_ALPHA</span>
            </div>
          </div>

          {/* BOTTOM PART: LIVE FEED TERMINAL */}
          <div className="hologram-card p-3 h-240px flex flex-col justify-between relative">
            <div className="corner-decor-tr"></div>
            <div className="corner-decor-bl"></div>

            <div className="flex justify-between items-center mb-2">
              <h2 className="text-sm font-bold font-title tracking-wider neon-text-cyan flex items-center gap-2">
                <Terminal className="w-4 h-4" /> LIVE INTEL TRANSMISSION
              </h2>
              <span className="text-9px font-mono text-cyan-600 flex items-center gap-1">
                <Radio className="w-3 h-3 blink text-cyan-400" /> WSS STREAM
              </span>
            </div>

            {/* Live Swap Streams */}
            <div className="flex-1 overflow-y-auto space-y-1-5 font-mono text-10px pr-1">
              {transactions.map(tx => (
                <div 
                  key={tx.signature}
                  onClick={() => {
                    setSelectedTx(tx);
                    playSound(440, 'sine', 0.1);
                  }}
                  className={`p-2 border rounded cursor-pointer transition-all ${
                    selectedTx?.signature === tx.signature 
                      ? 'border-cyan-400 bg-cyan-950-30' 
                      : 'border-cyan-950-40 bg-cyan-950-5 hover-border-cyan-900'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-cyan-400 truncate max-w-[120px]">{tx.walletName}</span>
                    <span className={`px-1 rounded text-8px font-black ${tx.action === 'BUY' ? 'bg-cyan-950 text-cyan-400 border border-cyan-500-30' : 'bg-orange-950 text-orange-400 border border-orange-500-30'}`}>
                      {tx.action}
                    </span>
                  </div>
                  <div className="flex justify-between items-center mt-1 text-cyan-600">
                    <span>
                      {tx.amountSol.toFixed(2)} SOL → <span className="text-cyan-400 font-bold">{tx.tokenSymbol}</span>
                    </span>
                    <span>{tx.timestamp}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* PANEL RIGHT: DETAILED TOKEN & HOLDER INTEL (col-span-4) */}
        <section className="lg-col-span-4 hologram-card p-3 flex flex-col justify-between h-300px lg-h-calc-100vh-140px min-h-500px">
          <div className="corner-decor-tr"></div>
          <div className="corner-decor-bl"></div>

          {/* Panel Header */}
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-sm font-bold font-title tracking-wider neon-text-cyan flex items-center gap-2">
              <Layers className="w-4 h-4" /> TOKENOMIC TELEMETRY
            </h2>
            <span className="text-10px font-mono text-cyan-500 border border-cyan-800 px-1">
              SYS: SECURE
            </span>
          </div>

          {selectedTx ? (
            <div className="flex-1 flex flex-col justify-between font-mono text-xs">
              
              {/* Asset Identity Block */}
              <div className="space-y-2 border-b border-cyan-950-60 pb-3">
                <div className="text-10px text-cyan-600">SELECTED TARGET ASSET</div>
                <div className="text-lg font-bold text-cyan-400 font-title neon-text-cyan">
                  {selectedTx.tokenName} ({selectedTx.tokenSymbol})
                </div>
                
                {/* Contract address copy helper */}
                <div className="bg-cyan-950-20 border border-cyan-950 rounded p-2 flex justify-between items-center text-10px">
                  <span className="text-cyan-600 truncate mr-2">ADDR: {selectedTx.tokenAddress}</span>
                  <button 
                    onClick={() => handleCopy(selectedTx.tokenAddress)}
                    className="p-1 rounded text-cyan-400 hover-text-cyan-300"
                    title="Copy Address"
                  >
                    {copiedAddress === selectedTx.tokenAddress ? <Check className="w-3-5 h-3-5 text-green-400" /> : <Copy className="w-3-5 h-3-5" />}
                  </button>
                </div>
              </div>

              {/* Holographic Stats Parameters */}
              <div className="grid grid-cols-2 gap-2 my-3">
                <div className="p-2 border border-cyan-950 bg-cyan-950-10 rounded">
                  <div className="text-9px text-cyan-600">MARKET CAP</div>
                  <div className="text-sm font-bold text-cyan-400">{selectedTx.marketCap}</div>
                </div>
                <div className="p-2 border border-cyan-950 bg-cyan-950-10 rounded">
                  <div className="text-9px text-cyan-600">AGE IN DAYS</div>
                  <div className="text-sm font-bold text-cyan-400">{selectedTx.ageDays.toFixed(1)} Days</div>
                </div>
                <div className="p-2 border border-cyan-950 bg-cyan-950-10 rounded">
                  <div className="text-9px text-cyan-600">LIQUIDITY SWAP</div>
                  <div className="text-sm font-bold text-cyan-400">{selectedTx.platform}</div>
                </div>
                <div className="p-2 border border-cyan-950 bg-cyan-950-10 rounded">
                  <div className="text-9px text-cyan-600">USD VALUE</div>
                  <div className="text-sm font-bold text-cyan-400">${selectedTx.usdValue.toFixed(2)}</div>
                </div>
              </div>

              {/* Holder categorization display (whales, dolphins, shrimps) */}
              <div className="flex-1 flex flex-col justify-center space-y-3-5 my-3">
                <div className="text-10px text-cyan-600 mb-1">HOLDER CLASSIFICATION PROFILE</div>
                
                {/* Whale Gauge */}
                <div>
                  <div className="flex justify-between text-10px text-cyan-500 mb-1">
                    <span>🐳 WHALES (&gt;= 1.0% Supply)</span>
                    <span className="font-bold text-cyan-400">{selectedTx.whales} Wallets</span>
                  </div>
                  <div className="w-full bg-cyan-950-40 h-2 rounded border border-cyan-900 overflow-hidden">
                    <div 
                      className="bg-cyan-400 h-full shadow-[0_0_8px_rgba(0,240,255,0.7)] transition-all duration-500" 
                      style={{ width: `${Math.min(100, (selectedTx.whales / 30) * 100)}%` }}
                    ></div>
                  </div>
                </div>

                {/* Dolphin Gauge */}
                <div>
                  <div className="flex justify-between text-10px text-cyan-500 mb-1">
                    <span>🐬 DOLPHINS (0.1% - 1.0% Supply)</span>
                    <span className="font-bold text-cyan-400">{selectedTx.dolphins} Wallets</span>
                  </div>
                  <div className="w-full bg-cyan-950-40 h-2 rounded border border-cyan-900 overflow-hidden">
                    <div 
                      className="bg-cyan-500-80 h-full shadow-[0_0_8px_rgba(0,120,255,0.7)] transition-all duration-500" 
                      style={{ width: `${Math.min(100, (selectedTx.dolphins / 40) * 100)}%` }}
                    ></div>
                  </div>
                </div>

                {/* Shrimp Gauge */}
                <div>
                  <div className="flex justify-between text-10px text-cyan-500 mb-1">
                    <span>🦐 SHRIMPS (&lt; 0.1% Supply)</span>
                    <span className="font-bold text-cyan-400">{selectedTx.shrimps} Wallets</span>
                  </div>
                  <div className="w-full bg-cyan-950-40 h-2 rounded border border-cyan-900 overflow-hidden">
                    <div 
                      className="bg-orange-500 h-full shadow-[0_0_8px_rgba(255,136,0,0.7)] transition-all duration-500" 
                      style={{ width: `${Math.min(100, (selectedTx.shrimps / 12000) * 100)}%` }}
                    ></div>
                  </div>
                </div>
              </div>

              {/* View on DexScreener button */}
              <div className="border-t border-cyan-950-60 pt-3">
                <a 
                  href={`https://dexscreener.com/solana/${selectedTx.tokenAddress}`} 
                  target="_blank" 
                  rel="noreferrer"
                  onClick={() => playSound(800, 'sine', 0.1)}
                  className="w-full flex items-center justify-center gap-2 bg-cyan-950-30 border border-cyan-400 py-2-5 rounded font-title text-xs text-cyan-400 hover-shadow-glow hover-text-cyan-300 transition-all"
                >
                  <Eye className="w-4 h-4" /> VIEW ON DEXSCREENER
                </a>
              </div>

            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-cyan-800 font-mono text-center">
              <AlertTriangle className="w-8 h-8 mb-2 animate-bounce" />
              SELECT AN ASSET TO PLOT INTEL
            </div>
          )}
        </section>
      </div>

      {/* FOOTER SYSTEM STATUS */}
      <footer className="hologram-card p-2-5 mt-3 flex justify-between items-center text-10px font-mono text-cyan-600">
        <div className="corner-decor-tr"></div>
        <div className="corner-decor-bl"></div>
        
        <div>SYSTEM DIAGNOSTIC: READY // COGNITIVE MODULE_ACTIVE</div>
        <div className="flex gap-4">
          <span>HOST: AWS_EC2_NODE</span>
          <span className="sm-block">DB: SQLITE_PERSISTENT</span>
          <span>UPTIME: 14D 05H 22M</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
