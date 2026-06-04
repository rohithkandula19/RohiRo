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
    <div className="space-y-6">
      <div className="grid gap-3 md:grid-cols-3">
        {bals.map((b) => (
          <div key={b.id} className="card p-4">
            <div className="label">{b.name}</div>
            <div className="mt-1 text-[24px] font-semibold tracking-tight text-ink">
              ${b.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
            <div className="meta mt-1">Read-only</div>
          </div>
        ))}
      </div>

      <div className="card p-5">
        <div className="section-title">
          <h3>Last 30 days · spend</h3>
          <div className="text-[15px] font-semibold text-ink">${totalExp.toFixed(2)}</div>
        </div>
        <div className="mt-3 space-y-2.5">
          {exp.map((e) => {
            const pct = totalExp > 0 ? (e.total / totalExp) * 100 : 0;
            return (
              <div key={e.category}>
                <div className="flex items-baseline justify-between text-[12.5px]">
                  <span className="text-ink">{e.category}</span>
                  <span className="font-mono text-[11.5px] text-ink-muted">${e.total.toFixed(2)}</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-hover">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="card p-5">
        <div className="section-title">
          <h3>Subscriptions</h3>
          <span className="text-[11.5px] text-ink-subtle">{subs.length} active</span>
        </div>
        <table className="term-table">
          <thead>
            <tr>
              <th>Name</th>
              <th className="text-right">Monthly</th>
              <th className="text-right">Renews</th>
            </tr>
          </thead>
          <tbody>
            {subs.map((s) => (
              <tr key={s.id}>
                <td className="text-ink">{s.name}</td>
                <td className="text-right font-mono">${s.monthly.toFixed(2)}</td>
                <td className="text-right text-ink-muted">{s.renews}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
