"use client";
// Money: what solar saved, what NEPA cost, fuel the generator didn't burn, month by month.
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MoneyHistory, MoneyView } from "@/lib/types";
import { naira, useApi } from "@/lib/useApi";
import { Failed, Loading, Section } from "../Section";

export function Money({ code }: { code: string }) {
  const view = useApi<MoneyView>(`/api/sites/${code}/tools/money_view`);
  const hist = useApi<MoneyHistory>(`/api/sites/${code}/views/money_history?months=6`);
  const m = view.data;
  return (
    <Section title="Money" aside="last 30 days">
      {view.loading && <Loading what="savings" />}
      {(view.error || m?.error) && <Failed message={view.error ?? m?.error ?? ""} />}
      {m && !m.error && (
        <>
          <p className="font-display text-4xl font-bold text-charge">{naira(m.saved_by_solar_ngn)}</p>
          <p className="text-sm text-muted">saved by solar in {m.period_days} days</p>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-muted">Spent on NEPA</dt>
              <dd className="font-display text-xl font-semibold text-nepa">{naira(m.nepa_cost_ngn)}</dd>
              <dd className="text-xs text-muted">{m.nepa_bought_kwh} kWh · {m.tariff}</dd>
            </div>
            {m.generator_fuel_avoided_litres !== undefined && (
              <div>
                <dt className="text-muted">Fuel not burned</dt>
                <dd className="font-display text-xl font-semibold">{m.generator_fuel_avoided_litres} litres</dd>
                <dd className="text-xs text-muted">{m.fuel_price}</dd>
              </div>
            )}
          </dl>
        </>
      )}
      {(hist.data?.months.length ?? 0) > 1 && (
        <div className="mt-5 h-44">
          <ResponsiveContainer>
            <BarChart data={hist.data!.months} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#e3e8ee" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#5e6b80" }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "#5e6b80" }} width={44}
                     tickFormatter={(v: number) => `₦${Math.round(v / 1000)}k`} />
              <Tooltip formatter={(v: number) => naira(v)} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="saved_ngn" name="Saved by solar" fill="#1e9e6a" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="nepa_spend_ngn" name="Spent on NEPA" fill="#4c6ef5" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {m?.warning && <p className="mt-3 text-xs text-warn">Estimates: fuel and tariff prices haven&apos;t been updated yet.</p>}
    </Section>
  );
}
