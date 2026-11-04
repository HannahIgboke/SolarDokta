// A titled block of the dashboard.
export function Section({ title, aside, children, className = "" }: {
  title: string; aside?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={`rounded-xl border border-line bg-card p-5 ${className}`}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="shrink-0 font-display text-lg font-semibold">{title}</h2>
        {aside && <div className="text-sm text-muted">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="animate-pulse text-sm text-muted">Loading {what}…</p>;
}

export function Failed({ message }: { message: string }) {
  return <p className="text-sm text-alarm">{message}</p>;
}
