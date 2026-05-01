type Props = {
  kicker: string;
  title: string;
  subtitle?: string;
};

export function PageHeader({ kicker, title, subtitle }: Props) {
  return (
    <header className="mb-12 max-w-2xl">
      <div className="kicker mb-3">— {kicker}</div>
      <h1 className="headline text-[36px] tracking-tight text-ink">{title}</h1>
      {subtitle ? (
        <p className="mt-3 max-w-[480px] text-body text-ink-muted">{subtitle}</p>
      ) : null}
    </header>
  );
}
