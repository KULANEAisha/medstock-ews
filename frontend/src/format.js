export const STATUS_LABEL = { STOCKOUT_RISK: "Stockout risk", WATCH: "Watch", OK: "OK", SURPLUS: "Surplus" };
export const STATUS_KEY = { STOCKOUT_RISK: "risk", WATCH: "watch", OK: "ok", SURPLUS: "surplus" };

// Short names for the column headers; the full label stays in the tooltip and the stock card.
export const SHORT = {
  amoxicillin_dt: "Amoxicillin",
  al_6x4: "Malaria tablets",
  ors_zinc: "ORS and zinc",
  paracetamol: "Paracetamol",
};

// The ruler is square-root scaled so the 0 to 1 month danger zone gets real width.
const MAX_MONTHS = 8;
export const rulerPos = (m) => Math.sqrt(Math.min(Math.max(m ?? 0, 0), MAX_MONTHS) / MAX_MONTHS);
export const TICKS = [1, 2, 6].map((m) => ({ m, pos: rulerPos(m) }));

export const fmtMonths = (m) => (m == null ? "n/a" : m.toFixed(1));
export const fmtNum = (n) => (n == null ? "n/a" : Math.round(n).toLocaleString("en-US"));
export const fmtDate = (iso) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
export const monthShort = (iso) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { month: "short" });
