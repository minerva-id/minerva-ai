import { useState } from 'react';
import type { ReactNode, MouseEvent } from 'react';

export default function HoloContainer({ children }: { children: ReactNode }) {
  const [rotate, setRotate] = useState({ x: 0, y: 0 });

  const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    setRotate({ x: -y / 30, y: x / 30 });
  };

  const handleMouseLeave = () => {
    setRotate({ x: 0, y: 0 });
  };

  return (
    <div 
      className="holo-container"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      <div 
        className="holo-content"
        style={{
          transform: `perspective(800px) rotateX(${rotate.x}deg) rotateY(${rotate.y}deg)`
        }}
      >
        {children}
      </div>
    </div>
  );
}
