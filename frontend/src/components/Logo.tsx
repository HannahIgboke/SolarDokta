// The SolarDokta mark: a sun rising behind a solar panel (reads on dark and light backgrounds).
export function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <circle cx="20" cy="11" r="7" fill="#f2b705" />
      <path d="M4 28 L9 14 H27 L22 28 Z" fill="#3b5b92" stroke="#eef2f5" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M6.6 21 H24.4 M15.5 14 L13 28 M21.5 14 L19 28" stroke="#eef2f5" strokeWidth="1.2" />
    </svg>
  );
}
