import { useEffect, useState } from 'react';

interface BootSequenceProps {
  onComplete: () => void;
}

export default function BootSequence({ onComplete }: BootSequenceProps) {
  const [lines, setLines] = useState<string[]>([]);
  const [done, setDone] = useState(false);

  const bootSteps = [
    { text: 'Memory Core .......................... ', delay: 200 },
    { text: 'OK', delay: 400, append: true, color: 'var(--teal)' },
    { text: 'WebSocket Relay ...................... ', delay: 600 },
    { text: 'OK', delay: 800, append: true, color: 'var(--teal)' },
    { text: 'Exchange Gateway ..................... ', delay: 1000 },
    { text: 'OK', delay: 1200, append: true, color: 'var(--teal)' },
    { text: 'MCP Bridge ........................... ', delay: 1500 },
    { text: 'OK', delay: 1700, append: true, color: 'var(--teal)' },
    { text: 'Hermes Agent Link .................... ', delay: 2000 },
    { text: 'STANDBY', delay: 2500, append: true, color: 'var(--amber)' },
    { text: 'All systems online. Good morning.', delay: 3200, isFinal: true },
  ];

  useEffect(() => {
    let timeoutIds: ReturnType<typeof setTimeout>[] = [];

    bootSteps.forEach((step) => {
      const id = setTimeout(() => {
        setLines((prev) => {
          const newLines = [...prev];
          if (step.append && newLines.length > 0) {
            newLines[newLines.length - 1] += `<b style="color:${step.color || 'inherit'}">${step.text}</b>`;
          } else {
            newLines.push(step.text);
          }
          return newLines;
        });

        if (step.isFinal) {
          setTimeout(() => {
            setDone(true);
            setTimeout(onComplete, 700); // Wait for fade out
          }, 1500);
        }
      }, step.delay);
      timeoutIds.push(id);
    });

    return () => timeoutIds.forEach(clearTimeout);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div id="boot" className={done ? 'done' : ''}>
      <div id="bootLogo">M I N E R V A</div>
      <div id="bootSub">TRADING INTELLIGENCE HUD</div>
      <div id="bootLines">
        {lines.map((line, i) => (
          <div key={i} dangerouslySetInnerHTML={{ __html: line }} />
        ))}
      </div>
    </div>
  );
}
