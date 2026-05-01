export function Divider({ label }: { label: string }) {
  return (
    <div className="my-10">
      <div className="kicker divider-label">{label}</div>
    </div>
  );
}
