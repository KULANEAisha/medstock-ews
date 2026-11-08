import { useEffect, useMemo, useState } from "react";
import Assistant from "./Assistant.jsx";
import Ledger from "./Ledger.jsx";
import StockCard from "./StockCard.jsx";
import { API_URL } from "./config.js";
import { fmtDate } from "./format.js";

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [waking, setWaking] = useState(false);
  const [selected, setSelected] = useState(null);
  const [prefill, setPrefill] = useState(null);

  async function load() {
    setError("");
    setWaking(false);
    const timer = setTimeout(() => setWaking(true), 4000);
    try {
      const res = await fetch(`${API_URL}/overview`);
      if (!res.ok) throw new Error(String(res.status));
      setData(await res.json());
    } catch {
      setError("Can't load the stock data. The server may be asleep or offline.");
    } finally {
      clearTimeout(timer);
      setWaking(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function select(sel) {
    setSelected(sel);
    // On narrow screens the card sits below the ledger, so bring it into view.
    if (window.matchMedia("(max-width: 1019px)").matches) {
      requestAnimationFrame(() => document.getElementById("stockcard")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  }

  const headline = useMemo(() => {
    if (!data) return null;
    const total = data.facilities.length;
    const atRisk = data.facilities.filter((f) => Object.values(f.cells).some((c) => c.status === "STOCKOUT_RISK")).length;
    return { total, atRisk };
  }, [data]);

  return (
    <div className="page">
      <header className="masthead">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span>MedStock early warning</span>
        </div>
        <p className="synthetic" role="note">
          Synthetic demo data, not real facilities
        </p>
      </header>

      <section className="hero" aria-live="polite">
        {headline ? (
          <>
            <h1>
              {headline.atRisk} of {headline.total} facilities have less than a month of stock on at least one medicine.
            </h1>
            <p className="hero-sub">
              Data as of {fmtDate(data.as_of)}. Months of stock is stock on hand divided by average monthly use over the
              last 3 months.
            </p>
          </>
        ) : error ? (
          <>
            <h1>The stock data didn't load.</h1>
            <p className="hero-sub">{error}</p>
            <button type="button" className="retry" onClick={load}>
              Try again
            </button>
          </>
        ) : (
          <>
            <h1 className="loading-title">Loading stock data</h1>
            <p className="hero-sub">
              {waking
                ? "The free server is waking up. This can take up to a minute the first time."
                : "Fetching the latest stock position."}
            </p>
          </>
        )}
      </section>

      {data && (
        <div className="layout">
          <Ledger data={data} selected={selected} onSelect={select} />
          <aside className="side">
            <StockCard
              data={data}
              selected={selected}
              onAsk={(text) => setPrefill({ text, nonce: Date.now() })}
            />
            <Assistant prefill={prefill} />
          </aside>
        </div>
      )}

      <footer className="site-footer">
        <p>
          Redistribution suggestions are for a person to review, not instructions. Built with a Python forecast and rules
          engine, a tool-calling language model and a FastAPI backend.
        </p>
      </footer>
    </div>
  );
}
