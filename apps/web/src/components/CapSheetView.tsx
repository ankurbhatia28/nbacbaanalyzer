"use client";

/**
 * One team's cap sheet (7.5): where its two totals sit against the four lines,
 * then every line on its books, with what each counts toward.
 *
 * Two bars, not one, on purpose. Team Salary (holds included) answers "does it
 * have room?"; Apron Team Salary (holds excluded) answers the tax and apron
 * questions. A single bar would have to pick one and be wrong about the other.
 */

import { useEffect, useState } from "react";

import { AskError } from "@/lib/ask";
import { datasetSummary, formatDate, shortSeason, sourceName } from "@/lib/format";
import {
  type CapSheet,
  type Line,
  KIND_LABEL,
  OPTION_LABEL,
  STATUS_LABEL,
  describeOver,
  dollars,
  fetchSheet,
  lineName,
  marks,
  millions,
  percent,
  scaleMax,
} from "@/lib/sheet";

type View = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; sheet: CapSheet };

export function CapSheetView({ team }: { team: string }) {
  const [view, setView] = useState<View>({ kind: "loading" });

  useEffect(() => {
    let live = true;
    setView({ kind: "loading" });
    fetchSheet(team).then(
      (sheet) => live && setView({ kind: "ready", sheet }),
      (error: unknown) =>
        live &&
        setView({
          kind: "error",
          message: error instanceof AskError ? error.message : String(error),
        }),
    );
    return () => {
      live = false;
    };
  }, [team]);

  if (view.kind === "loading") return <p className="muted">Loading the cap sheet…</p>;
  if (view.kind === "error") {
    return (
      <div className="error" role="alert">
        <p>{view.message}</p>
      </div>
    );
  }
  return <Sheet sheet={view.sheet} />;
}

function Sheet({ sheet }: { sheet: CapSheet }) {
  const season = shortSeason(sheet.season);
  return (
    <article className="sheet">
      <header className="sheet-header">
        <h2>{sheet.name}</h2>
        <p className="muted">
          {season} · <strong className="sheet-status">{STATUS_LABEL[sheet.status]}</strong>
          {sheet.ceiling ? ` · hard-capped at the ${sheet.ceiling.level.replace("_", " ")}` : ""}
        </p>
      </header>

      {sheet.warnings.length > 0 && (
        <ul className="warnings">
          {sheet.warnings.map((w) => (
            <li key={w} className="warning">
              {w}
            </li>
          ))}
        </ul>
      )}

      <Bars sheet={sheet} />
      <Standing sheet={sheet} />
      <Lines sheet={sheet} />
      {sheet.trade_exceptions.length > 0 && <Exceptions sheet={sheet} />}

      <footer className="card-footer muted">
        <p>
          {season} salaries: {sourceName("fanspo")}'s payroll
          {sheet.sources.fanspo ? `, scraped ${formatDate(sheet.sources.fanspo)}` : ""}. Later
          seasons: {sourceName("bbref_contracts")}
          {sheet.sources.bbref_contracts ? `, scraped ${formatDate(sheet.sources.bbref_contracts)}` : ""}.
          {sheet.ceiling && sheet.sources.salaryswish
            ? ` Hard caps: ${sourceName("salaryswish")}, scraped ${formatDate(sheet.sources.salaryswish)}.`
            : ""}
        </p>
        {sheet.dataset && <p>Dataset: {datasetSummary(sheet.dataset)}</p>}
      </footer>
    </article>
  );
}

function Bars({ sheet }: { sheet: CapSheet }) {
  const max = scaleMax(sheet);
  const lines = marks(sheet).filter((m) => m.key !== "ceiling");
  const hardAt = sheet.ceiling?.level;
  const bars = [
    { key: "cap", label: "Team Salary", note: "holds included · measured against the cap", amount: sheet.totals.cap },
    { key: "apron", label: "Apron Team Salary", note: "holds excluded · measured against the tax and aprons", amount: sheet.totals.apron },
  ];
  return (
    <figure className="bars" aria-label="Salary totals against the thresholds">
      <ul className="bar-legend">
        {bars.map((b) => (
          <li key={b.key}>
            <span className={`swatch bar-${b.key}`} aria-hidden="true" />
            <strong>{b.label}</strong> <span className="num">{dollars(b.amount)}</span>
            <span className="muted"> · {b.note}</span>
          </li>
        ))}
      </ul>
      <div className="bars-plot">
        {bars.map((b) => (
          <div key={b.key} className="bar-track">
            <div className={`bar bar-${b.key}`} style={{ width: `${percent(b.amount, max)}%` }} />
          </div>
        ))}
        <div className="threshold-layer" aria-hidden="true">
          {lines.map((m, i) => (
            <div
              key={m.key}
              className={`threshold${m.key === hardAt ? " threshold-hard" : ""} threshold-${i % 2 ? "low" : "high"}${percent(m.amount, max) > 85 ? " threshold-end" : ""}`}
              style={{ left: `${percent(m.amount, max)}%` }}
            >
              <span className="threshold-label">{m.key === hardAt ? `${m.short} · hard cap` : m.short}</span>
            </div>
          ))}
        </div>
      </div>
    </figure>
  );
}

function Standing({ sheet }: { sheet: CapSheet }) {
  return (
    <section className="section">
      <h3>Against each line</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Line</th>
              <th className="num">Amount</th>
              <th className="wide-only">Measured with</th>
              <th className="num">Position</th>
            </tr>
          </thead>
          <tbody>
            {marks(sheet).map((m) => (
              <tr key={m.key} className={m.over > 0 ? "over" : undefined}>
                <td>{m.label}</td>
                <td className="num">{dollars(m.amount)}</td>
                <td className="wide-only">{m.against === "cap" ? "Team Salary" : "Apron Team Salary"}</td>
                <td className="num">{describeOver(m.over)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Lines({ sheet }: { sheet: CapSheet }) {
  const season = sheet.season;
  const later = sheet.later_seasons;
  const counted = (line: Line) =>
    line.counts.apron === line.counts.cap ? "Both" : line.counts.apron === 0 ? "Cap only" : `Aprons at ${millions(line.counts.apron)}`;
  return (
    <section className="section">
      <h3>The books</h3>
      <div className="table-scroll">
        <table className="sheet-lines">
          <thead>
            <tr>
              <th>Player</th>
              <th className="wide-only">Kind</th>
              <th className="num">{shortSeason(season)}</th>
              <th>Counts toward</th>
              {later.map((s) => (
                <th key={s} className="num">
                  {shortSeason(s)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.lines.map((line, i) => (
              <tr key={`${line.kind}-${line.player ?? i}-${i}`} className={`line-${line.kind}`}>
                <td>
                  {lineName(line)}
                  {line.kind !== "contract" && <span className="narrow-only muted"> · {KIND_LABEL[line.kind]}</span>}
                </td>
                <td className="wide-only">
                  {KIND_LABEL[line.kind]}
                  {line.label ? <span className="muted"> · {line.label}</span> : null}
                </td>
                <td className="num">
                  {dollars(line.amount)}
                  <Option code={line.options[season]} />
                </td>
                <td>{counted(line)}</td>
                {later.map((s) => (
                  <td key={s} className="num">
                    {line.later[s] ? dollars(line.later[s]) : ""}
                    <Option code={line.later[s] ? line.options[s] : undefined} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th>Committed (contracts)</th>
              <th className="wide-only" />
              <td className="num">{dollars(sheet.totals.committed)}</td>
              <td />
              {later.map((s) => (
                <td key={s} className="num">
                  {dollars(sheet.later_totals[s] ?? 0)}
                </td>
              ))}
            </tr>
            <tr>
              <th>Team Salary</th>
              <th className="wide-only" />
              <td className="num">{dollars(sheet.totals.cap)}</td>
              <td colSpan={1 + later.length} className="muted">
                every line
              </td>
            </tr>
            <tr>
              <th>Apron Team Salary</th>
              <th className="wide-only" />
              <td className="num">{dollars(sheet.totals.apron)}</td>
              <td colSpan={1 + later.length} className="muted">
                holds out, qualifying offers in
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      {later.length > 0 && (
        <p className="muted small">
          Later seasons list contracts only: holds and dead cap for those seasons are not in the
          data. PO, TO and ETO mark a player option, team option or early termination option.
        </p>
      )}
    </section>
  );
}

function Option({ code }: { code: string | undefined }) {
  if (!code) return null;
  return <span className="option-tag"> {OPTION_LABEL[code] ?? code}</span>;
}

function Exceptions({ sheet }: { sheet: CapSheet }) {
  return (
    <section className="section">
      <h3>Trade exceptions</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>From</th>
              <th className="num">Available</th>
              <th>Expires</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {sheet.trade_exceptions.map((t, i) => (
              <tr key={i} className={t.expired ? "expired" : undefined}>
                <td>{t.reason ?? <span className="muted">not given</span>}</td>
                <td className="num">{dollars(t.available ?? t.amount)}</td>
                <td>
                  {t.expires && /^\d{4}-\d{2}-\d{2}$/.test(t.expires) ? formatDate(t.expires) : (t.expires ?? "—")}
                  {t.expired ? <strong> · expired</strong> : null}
                </td>
                <td className="muted">
                  {sourceName(t.source)}
                  {t.as_of ? `, as of ${formatDate(t.as_of)}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
