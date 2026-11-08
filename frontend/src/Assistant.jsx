import { useEffect, useRef, useState } from "react";
import Answer from "./Answer.jsx";
import { API_URL } from "./config.js";

const MAX_CHARS = 500;
const TIMEOUT_MS = 90_000; // free hosting can take about a minute to wake up

const EXAMPLES = [
  "Which facilities in District A are at high risk of running out of amoxicillin?",
  "Which facilities could run out of ORS and zinc within the next 8 weeks?",
  "Which facilities have surplus amoxicillin?",
  "Where could surplus amoxicillin be moved to help F14?",
  "What is the stock level of amoxicillin at F02?",
];

function friendlyError(status, detail) {
  if (status === 429) return "Too many questions in a short time. Wait a minute, then try again.";
  if (status === 422) return `Enter a question between 3 and ${MAX_CHARS} characters.`;
  if (status >= 500) return typeof detail === "string" ? detail : "The assistant is unavailable. Try again.";
  return "Something went wrong. Try again.";
}

export default function Assistant({ prefill }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!prefill) return;
    setQuestion(prefill.text);
    inputRef.current?.focus();
    inputRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [prefill]);

  async function ask(q) {
    const text = q.trim();
    if (text.length < 3 || loading) return;
    setLoading(true);
    setSlow(false);
    setError("");
    const slowTimer = setTimeout(() => setSlow(true), 5000);
    const controller = new AbortController();
    const abortTimer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    const started = performance.now();
    try {
      const res = await fetch(`${API_URL}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
        signal: controller.signal,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(friendlyError(res.status, data.detail));
        return;
      }
      setHistory((h) => [{ id: Date.now(), question: text, ms: Math.round(performance.now() - started), ...data }, ...h]);
      setQuestion("");
    } catch (e) {
      setError(
        e.name === "AbortError"
          ? "The server took too long to respond. Try again in a moment."
          : "Can't reach the server. Check your connection, then try again."
      );
    } finally {
      clearTimeout(slowTimer);
      clearTimeout(abortTimer);
      setLoading(false);
      setSlow(false);
    }
  }

  return (
    <section className="assistant" aria-label="Assistant">
      <h2>Ask about stock</h2>
      <p className="assistant-lede">
        Answers come only from the stock data, through fixed tools. If something is missing, the assistant says so.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <label htmlFor="q" className="sr-only">
          Your question
        </label>
        <textarea
          id="q"
          ref={inputRef}
          value={question}
          onChange={(e) => setQuestion(e.target.value.slice(0, MAX_CHARS))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(question);
            }
          }}
          placeholder="Which facilities in District B could run out of paracetamol within 8 weeks?"
          rows={3}
          disabled={loading}
        />
        <div className="ask-row">
          <span className="count">
            {question.length} of {MAX_CHARS}
          </span>
          <button type="submit" disabled={loading || question.trim().length < 3}>
            {loading ? "Checking the data" : "Ask"}
          </button>
        </div>
      </form>

      {history.length === 0 && (
        <ul className="examples" aria-label="Example questions">
          {EXAMPLES.map((ex) => (
            <li key={ex}>
              <button
                type="button"
                onClick={() => {
                  setQuestion(ex);
                  inputRef.current?.focus();
                }}
                disabled={loading}
              >
                {ex}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div aria-live="polite" className="status-area">
        {loading && slow && (
          <p className="notice">The free server may be waking up. The first question can take up to a minute.</p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="results">
        {history.map((item) => (
          <article key={item.id} className="reply">
            <p className="q">{item.question}</p>
            <Answer text={item.answer} />
            <p className="meta">
              {item.tools_called?.length > 0
                ? `Looked up with ${[...new Set(item.tools_called.map((t) => t.tool))].join(", ")}`
                : "No data lookup needed"}
              . {item.model}
              {item.cached ? ", cached" : ""}, {(item.ms / 1000).toFixed(1)} s.
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
