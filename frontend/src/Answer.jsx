// Renders the assistant's answer (light markdown: **bold**, `code`, bullet/numbered lists)
// without dangerouslySetInnerHTML, and turns status words into coloured chips.
const STATUS = /\b(STOCKOUT_RISK|WATCH|SURPLUS|OK)\b/g;
const STATUS_CLASS = { STOCKOUT_RISK: "risk", WATCH: "watch", SURPLUS: "surplus", OK: "ok" };

function withStatusChips(text, keyBase) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(STATUS)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(
      <span key={`${keyBase}-${m.index}`} className={`chip chip-${STATUS_CLASS[m[1]]}`}>
        {m[1] === "STOCKOUT_RISK" ? "STOCKOUT RISK" : m[1]}
      </span>
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function inline(text, keyBase = "i") {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((part, i) => {
    const key = `${keyBase}-${i}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4)
      return <strong key={key}>{withStatusChips(part.slice(2, -2), key)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
      return <code key={key}>{part.slice(1, -1)}</code>;
    return <span key={key}>{withStatusChips(part, key)}</span>;
  });
}

export default function Answer({ text }) {
  const blocks = [];
  let list = null;
  text.split("\n").forEach((raw, idx) => {
    const line = raw.trimEnd();
    const item = line.match(/^\s*(?:[*-]|\d+\.)\s+(.*)$/);
    if (item) {
      const ordered = /^\s*\d+\./.test(line);
      if (!list || list.ordered !== ordered) {
        list = { ordered, items: [], key: `l${idx}` };
        blocks.push(list);
      }
      list.items.push(item[1]);
    } else {
      list = null;
      if (line.trim()) blocks.push({ p: line, key: `p${idx}` });
    }
  });

  return (
    <div className="answer-body">
      {blocks.map((b) => {
        if (b.p !== undefined) return <p key={b.key}>{inline(b.p, b.key)}</p>;
        const Tag = b.ordered ? "ol" : "ul";
        return (
          <Tag key={b.key}>
            {b.items.map((it, i) => (
              <li key={i}>{inline(it, `${b.key}-${i}`)}</li>
            ))}
          </Tag>
        );
      })}
    </div>
  );
}
