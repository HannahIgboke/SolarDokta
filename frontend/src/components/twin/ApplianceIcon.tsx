// Simple line icons for appliances, drawn in a 24x24 box with the current text colour.
type Props = { name: string; x: number; y: number; size?: number };

function glyph(name: string) {
  const n = name.toLowerCase();
  if (/fridge|freezer/.test(n))
    return <><rect x="6" y="2.5" width="12" height="19" rx="1.5" /><path d="M6 10h12M9 5.5v2.5M9 12.5v3" /></>;
  if (/\bac\b|^ac /.test(n))
    return <><rect x="2.5" y="5" width="19" height="8" rx="2" /><path d="M5 10h14M7 16l-1 3M12 16v3M17 16l1 3" /></>;
  if (/fan/.test(n))
    return <><circle cx="12" cy="10" r="1.6" /><path d="M12 8.4C11 4 15 3 15.5 6.5 13.5 7.5 13 8 12 8.4ZM13.4 11c4 1.5 3.5 5.5 0 4.6-.4-2-.6-2.7 0-4.6ZM10.6 10.6c-3.4 2.7-6.4 0-3.8-2.3 1.7 1 2.3 1.3 3.8 2.3ZM12 11.6V21M8.5 21h7" /></>;
  if (/light|bulb/.test(n))
    return <><path d="M9 17h6M10 20h4M8.5 13.5a5.5 5.5 0 1 1 7 0c-.9.8-1.5 1.8-1.5 3h-4c0-1.2-.6-2.2-1.5-3Z" /></>;
  if (/tv|projector|screen/.test(n))
    return <><rect x="2.5" y="4.5" width="19" height="12" rx="1.5" /><path d="M9 20.5h6M12 16.5v4" /></>;
  if (/iron/.test(n))
    return <><path d="M3 17h15.5c1.4 0 2.5-1 2.5-2.4C21 10 17.5 8 13 8H9c-2.5 0-4.5 3.5-6 9Z" /><path d="M9 8c0-2 1.2-3 3-3h4" /></>;
  if (/pump|borehole/.test(n))
    return <><path d="M12 3.5c3 4 5 6.6 5 9.3a5 5 0 0 1-10 0c0-2.7 2-5.3 5-9.3Z" /><path d="M10 14a2 2 0 0 0 2 2" /></>;
  if (/microwave|steriliz|centrifuge/.test(n))
    return <><rect x="2.5" y="5" width="19" height="14" rx="1.5" /><rect x="5" y="8" width="10" height="8" rx="1" /><path d="M18 9v.01M18 12v.01" /></>;
  if (/washing/.test(n))
    return <><rect x="4" y="2.5" width="16" height="19" rx="2" /><circle cx="12" cy="13" r="4.5" /><path d="M7 6h3" /></>;
  if (/laptop|computer|office|phone/.test(n))
    return <><rect x="5" y="5" width="14" height="10" rx="1" /><path d="M2.5 18.5h19l-2-3.5h-15l-2 3.5Z" /></>;
  if (/router|cctv/.test(n))
    return <><path d="M5 12.5a10 10 0 0 1 14 0M8 15.5a5.5 5.5 0 0 1 8 0" /><circle cx="12" cy="18.5" r="1.2" /></>;
  return <><path d="M13 2.5 5.5 13.5h6l-1 8 8-11.5h-6l.5-7.5Z" /></>;
}

export function ApplianceIcon({ name, x, y, size = 20 }: Props) {
  return (
    <svg x={x} y={y} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {glyph(name)}
    </svg>
  );
}
