import { useMemo, useState } from "react";
import { SHORT, STATUS_KEY, STATUS_LABEL, TICKS, fmtMonths, rulerPos } from "./format.js";

function Cell({ cell, selected, onSelect, label }) {
  if (!cell) {
    return (
      <td className="cell-wrap">
        <span className="cell cell-none" title="This facility has no stock record for this medicine">
          no record
        </span>
      </td>
    );
  }
  const key = STATUS_KEY[cell.status];
  const out = cell.stock === 0;
  return (
    <td className="cell-wrap">
      <button
        type="button"
        className={`cell s-${key}${selected ? " is-selected" : ""}`}
        onClick={onSelect}
        aria-pressed={selected}
        aria-label={`${label}: ${STATUS_LABEL[cell.status]}, ${out ? "out of stock" : fmtMonths(cell.months) + " months of stock"}`}
      >
        <span className="cell-top">
          <span className="mos">{out ? "Out" : fmtMonths(cell.months)}</span>
          {!out && <span className="mos-unit">mo</span>}
        </span>
        <span className="ruler" aria-hidden="true">
          <span className="fill" style={{ "--w": rulerPos(cell.months) }} />
        </span>
      </button>
    </td>
  );
}

export default function Ledger({ data, selected, onSelect }) {
  const [district, setDistrict] = useState("All");
  const [sort, setSort] = useState("urgent");

  const districts = useMemo(() => ["All", ...new Set(data.facilities.map((f) => f.district))].sort(), [data]);

  const rows = useMemo(() => {
    const worst = (f) => Math.min(...Object.values(f.cells).map((c) => c.months ?? Infinity), Infinity);
    const list = data.facilities.filter((f) => district === "All" || f.district === district);
    return [...list].sort((a, b) => (sort === "urgent" ? worst(a) - worst(b) || a.id.localeCompare(b.id) : a.id.localeCompare(b.id)));
  }, [data, district, sort]);

  return (
    <section className="ledger" aria-label="Stock ledger">
      <div className="ledger-controls">
        <div className="seg" role="group" aria-label="District">
          {districts.map((d) => (
            <button key={d} type="button" aria-pressed={district === d} onClick={() => setDistrict(d)}>
              {d === "All" ? "All districts" : d}
            </button>
          ))}
        </div>
        <div className="seg" role="group" aria-label="Sort order">
          <button type="button" aria-pressed={sort === "urgent"} onClick={() => setSort("urgent")}>
            Most urgent first
          </button>
          <button type="button" aria-pressed={sort === "id"} onClick={() => setSort("id")}>
            By facility
          </button>
        </div>
      </div>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col" className="fac-col">
                Facility
              </th>
              {data.commodities.map((c) => {
                const n = data.counts[c.code];
                return (
                  <th scope="col" key={c.code} title={c.label}>
                    <span className="col-name">{SHORT[c.code] ?? c.label}</span>
                    <span className="col-sub">
                      {n.STOCKOUT_RISK} at risk, {n.WATCH} watch
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.id}>
                <th scope="row" className="fac-col">
                  <span className="fac-id">{f.id}</span>
                  <span className="fac-meta">
                    {f.district.replace("District ", "District ")}, {f.level.replace("_", " ")}
                  </span>
                </th>
                {data.commodities.map((c) => (
                  <Cell
                    key={c.code}
                    cell={f.cells[c.code]}
                    label={`${f.id} ${SHORT[c.code] ?? c.label}`}
                    selected={selected?.facility === f.id && selected?.commodity === c.code}
                    onSelect={() => onSelect({ facility: f.id, commodity: c.code })}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="legend">
        <div className="legend-ruler" aria-hidden="true">
          {TICKS.map((t) => (
            <span key={t.m} style={{ left: `${t.pos * 100}%` }}>
              {t.m}
            </span>
          ))}
        </div>
        <p>
          The ruler in each cell shows months of stock. Ticks mark 1, 2 and 6 months: under 1 is stockout risk, 1 to 2 is
          watch, 2 to 6 is OK, over 6 is surplus. Select a cell for details.
        </p>
      </div>
    </section>
  );
}
