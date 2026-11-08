import { SHORT, STATUS_KEY, STATUS_LABEL, fmtMonths, fmtNum, monthShort } from "./format.js";

function History({ items }) {
  const max = Math.max(...items.map((h) => h.stock), 1);
  return (
    <figure className="history">
      <svg viewBox="0 0 240 64" role="img" aria-label={`Stock on hand, last ${items.length} months: ${items.map((h) => fmtNum(h.stock)).join(", ")}`}>
        {items.map((h, i) => {
          const w = 240 / items.length;
          const bh = Math.max((h.stock / max) * 52, h.stock === 0 ? 1.5 : 2);
          return <rect key={h.month} x={i * w + 6} y={56 - bh} width={w - 12} height={bh} rx="1.5" className="bar" />;
        })}
        <line x1="0" x2="240" y1="56.5" y2="56.5" className="axis" />
      </svg>
      <div className="history-labels">
        {items.map((h) => (
          <span key={h.month}>{monthShort(h.month)}</span>
        ))}
      </div>
      <figcaption>Stock on hand at month end</figcaption>
    </figure>
  );
}

export default function StockCard({ data, selected, onAsk }) {
  if (!selected) {
    return (
      <section id="stockcard" className="stockcard empty" aria-label="Stock card">
        <h2>Stock card</h2>
        <p>Select a cell in the ledger to see the numbers behind it.</p>
      </section>
    );
  }
  const fac = data.facilities.find((f) => f.id === selected.facility);
  const com = data.commodities.find((c) => c.code === selected.commodity);
  const cell = fac?.cells[selected.commodity];
  if (!fac || !com || !cell) return null;
  const key = STATUS_KEY[cell.status];

  return (
    <section id="stockcard" className={`stockcard s-${key}`} aria-label="Stock card" aria-live="polite">
      <h2>
        {fac.id}, {SHORT[com.code] ?? com.label}
      </h2>
      <p className="sc-sub">
        {fac.name}, {fac.district}
      </p>
      <p className={`stamp stamp-${key}`}>{STATUS_LABEL[cell.status]}</p>
      <dl>
        <div>
          <dt>On hand</dt>
          <dd>
            {fmtNum(cell.stock)} <span>{com.unit}</span>
          </dd>
        </div>
        <div>
          <dt>Average use per month</dt>
          <dd>{fmtNum(cell.avg_use)}</dd>
        </div>
        <div>
          <dt>Months of stock</dt>
          <dd>
            {fmtMonths(cell.months)} <span>({cell.weeks == null ? "n/a" : cell.weeks.toFixed(1)} weeks)</span>
          </dd>
        </div>
      </dl>
      <History items={cell.history} />
      <p className="calc">{cell.explanation.replace(" -> ", ", status: ").replace(/STOCKOUT_RISK|WATCH|OK|SURPLUS/, (s) => STATUS_LABEL[s])}</p>
      <button
        type="button"
        className="ask-about"
        onClick={() =>
          onAsk(
            cell.status === "STOCKOUT_RISK"
              ? `${fac.id} is about to run out of ${com.label}. Which nearby facility (within 60 km) has surplus and could supply it?`
              : `What is the stock status of ${com.label} at ${fac.id}?`
          )
        }
      >
        Ask the assistant about this
      </button>
    </section>
  );
}
