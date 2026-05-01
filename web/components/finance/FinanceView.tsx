"use client";

import { useEffect, useState } from "react";

type Balance = { id: string; name: string; balance: number; available: number };
type Expense = { category: string; total: number };
type Sub = { id: string; name: string; monthly: number; renews: string };

export function FinanceView() {
  const [bals, setBals] = useState<Balance[]>([]);
  const [exp, setExp] = useState<Expense[]>([]);
  const [subs, setSubs] = useState<Sub[]>([]);

  useEffect(() => {
    fetch("/api/finance/balances").then((r) => r.json()).then(setBals).catch(() => null);
    fetch("/api/finance/expenses").then((r) => r.json()).then(setExp).catch(() => null);
    fetch("/api/finance/subscriptions").then((r) => r.json()).then(setSubs).catch(() => null);
  }, []);

  const totalExp = exp.reduce((a, b) => a + b.total, 0);

  return (
    <div className="space-y-8">
      <div className="grid gap-3 md:grid-cols-3">
        {bals.map((b) => (
          <div key={b.id} className="card">
            <div className="kicker">{b.name}</div>
            <div className="mt-2 font-serif text-[28px]">${b.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
            <div className="kicker mt-1">read-only</div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="flex items-baseline justify-between">
          <div className="kicker">last 30 days · spend</div>
          <div className="font-serif text-[20px]">${totalExp.toFixed(2)}</div>
        </div>
        <div className="mt-3 space-y-2">
          {exp.map((e) => {
            const pct = totalExp > 0 ? (e.total / totalExp) * 100 : 0;
            return (
              <div key={e.category}>
                <div className="flex items-baseline justify-between text-[12.5px]">
                  <span className="text-ink">{e.category}</span>
                  <span className="font-mono text-[11px] text-ink-muted">${e.total.toFixed(2)}</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-accent-soft">
                  <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="card">
        <div className="kicker mb-3">subscriptions</div>
        <table className="w-full text-[13px]">
          <thead className="kicker text-ink-subtle">
            <tr>
              <th className="py-1 text-left">name</th>
              <th className="py-1 text-right">monthly</th>
              <th className="py-1 text-right">renews</th>
            </tr>
          </thead>
          <tbody>
            {subs.map((s) => (
              <tr key={s.id} className="border-t border-hair border-line-subtle">
                <td className="py-2">{s.name}</td>
                <td className="py-2 text-right font-mono">${s.monthly.toFixed(2)}</td>
                <td className="py-2 text-right text-ink-muted">{s.renews}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
