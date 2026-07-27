// src/components/layout/RobotIcon.tsx
interface RobotIconProps {
  size?: number;
  className?: string;
}

export default function RobotIcon({ size = 32, className = '' }: RobotIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="40 5 600 350"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        {/* Glow filter for antenna tip and eyes */}
        <filter id="robotGlow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="8" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {/* Floating Satellite Signal Dot-Cluster Left */}
      <g>
        <circle cx="95" cy="120" r="15" fill="#E1BC78" stroke="#85683c" strokeWidth="5" filter="url(#robotGlow)" />
        <circle cx="65" cy="90" r="10" fill="#C88B47" stroke="#85683c" strokeWidth="4" />
        <circle cx="115" cy="75" r="7" fill="#E1BC78" opacity="0.9" />
      </g>

      {/* Floating Satellite Signal Dot-Cluster Right */}
      <g>
        <circle cx="585" cy="120" r="15" fill="#E1BC78" stroke="#85683c" strokeWidth="5" filter="url(#robotGlow)" />
        <circle cx="615" cy="90" r="10" fill="#C88B47" stroke="#85683c" strokeWidth="4" />
        <circle cx="565" cy="75" r="7" fill="#E1BC78" opacity="0.9" />
      </g>

      {/* Left Ear Module */}
      <rect x="140" y="180" width="40" height="85" rx="12" ry="12" fill="#0a0f0c" stroke="#85683c" strokeWidth="10" />
      <line x1="160" y1="195" x2="160" y2="250" stroke="#C88B47" strokeWidth="8" strokeLinecap="round" />

      {/* Right Ear Module */}
      <rect x="500" y="180" width="40" height="85" rx="12" ry="12" fill="#0a0f0c" stroke="#85683c" strokeWidth="10" />
      <line x1="520" y1="195" x2="520" y2="250" stroke="#C88B47" strokeWidth="8" strokeLinecap="round" />

      {/* Antenna Stem */}
      <line x1="340" y1="110" x2="340" y2="48" stroke="#C88B47" strokeWidth="14" strokeLinecap="round" />

      {/* Antenna Tip Glowing Ball */}
      <circle cx="340" cy="36" r="24" fill="#E1BC78" stroke="#85683c" strokeWidth="6" filter="url(#robotGlow)" />
      <circle cx="340" cy="36" r="12" fill="#FFFFFF" opacity="0.9" />

      {/* Main Robot Head Outer Box */}
      <rect x="175" y="105" width="330" height="230" rx="46" ry="46" fill="#0a0f0c" stroke="#85683c" strokeWidth="14" />

      {/* Visor Screen Frame */}
      <rect x="205" y="135" width="270" height="170" rx="32" ry="32" fill="#050806" stroke="#C88B47" strokeWidth="8" />

      {/* Left Oval Glowing Eye */}
      <ellipse cx="275" cy="200" rx="32" ry="40" fill="#E1BC78" stroke="#85683c" strokeWidth="7" filter="url(#robotGlow)" />
      <ellipse cx="283" cy="190" rx="10" ry="14" fill="#FFFFFF" opacity="0.9" />

      {/* Right Oval Glowing Eye */}
      <ellipse cx="405" cy="200" rx="32" ry="40" fill="#E1BC78" stroke="#85683c" strokeWidth="7" filter="url(#robotGlow)" />
      <ellipse cx="413" cy="190" rx="10" ry="14" fill="#FFFFFF" opacity="0.9" />

      {/* Small Curved Smile Mouth */}
      <path d="M 300 262 Q 340 288 380 262" fill="none" stroke="#E1BC78" strokeWidth="10" strokeLinecap="round" />
    </svg>
  );
}
