type Props = { label: string; right?: React.ReactNode };

export function Divider({ label, right }: Props) {
  return (
    <div className="mb-3 mt-8 flex items-center justify-between">
      <h3 className="text-[12px] font-semibold text-ink-muted">{label}</h3>
      {right ? <div className="text-[11.5px] text-ink-subtle">{right}</div> : null}
    </div>
  );
}
