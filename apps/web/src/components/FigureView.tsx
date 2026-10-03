import type { Figure } from "@/lib/card";
import { describeObserved, formatCell } from "@/lib/format";

const MAX_ROWS = 12;

/**
 * One league-data query: the rows, where and when they were observed (7.6),
 * and the SQL that produced them, one click away (7.3).
 */
export function FigureView({ figure, index }: { figure: Figure; index: number }) {
  const rows = figure.rows.slice(0, MAX_ROWS);
  const hidden = figure.rows.length - rows.length;

  return (
    <div className="figure" id={`figure-${index}`}>
      {figure.in_answer.length > 0 && (
        <p className="figure-supplies">
          Supplies <span className="num">{figure.in_answer.join(", ")}</span> in the answer
        </p>
      )}

      {figure.rows.length === 0 ? (
        <p className="muted">This query matched no rows.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {figure.columns.map((c) => (
                  <th key={c} scope="col">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, r) => (
                <tr key={r}>
                  {figure.columns.map((c) => {
                    const value = row[c] ?? null;
                    return (
                      <td key={c} className={typeof value === "number" ? "num" : undefined}>
                        {formatCell(value)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {hidden > 0 && <p className="muted">and {hidden} more rows</p>}
        </div>
      )}

      {figure.provenance.length > 0 && (
        <ul className="provenance">
          {figure.provenance.map((o) => (
            <li key={`${o.source}:${o.basis}`} className={`basis-${o.basis}`}>
              {describeObserved(o)}
            </li>
          ))}
        </ul>
      )}

      <details className="query">
        <summary>Show the query</summary>
        <pre>{figure.sql}</pre>
        {figure.params.length > 0 && (
          <p className="muted">
            Parameters, in order: <code>{figure.params.map((p) => JSON.stringify(p)).join(", ")}</code>
          </p>
        )}
      </details>
    </div>
  );
}
