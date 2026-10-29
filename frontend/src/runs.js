// Converting a block's runs (text with formatting) to editable HTML and back.

const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function runsToHtml(runs) {
  return (runs || [])
    .map((r) => {
      let h = esc(r.text);
      if (r.superscript) h = `<sup>${h}</sup>`;
      else if (r.subscript) h = `<sub>${h}</sub>`;
      if (r.bold) h = `<b>${h}</b>`;
      if (r.italic) h = `<i>${h}</i>`;
      if (r.underline) h = `<u>${h}</u>`;
      if (r.strike) h = `<s>${h}</s>`;
      const cls = r.uncertain ? ' class="unc"' : "";
      const style = r.color ? ` style="color:${r.color}"` : "";
      if (cls || style) h = `<span${cls}${style}>${h}</span>`;
      return h;
    })
    .join("");
}

function toHex(color) {
  if (!color) return null;
  if (color.startsWith("#")) return color.length === 7 ? color.toUpperCase() : null;
  const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (!m) return null;
  const hex = "#" + [m[1], m[2], m[3]].map((n) => Number(n).toString(16).padStart(2, "0")).join("");
  return hex.toUpperCase() === "#000000" ? null : hex.toUpperCase();
}

const FLAGS = ["bold", "italic", "underline", "strike", "superscript", "subscript"];

export function htmlToRuns(root) {
  const runs = [];
  const walk = (node, fmt) => {
    if (node.nodeType === Node.TEXT_NODE) {
      if (node.nodeValue) runs.push({ ...fmt, text: node.nodeValue.replace(/ /g, " ") });
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const tag = node.tagName;
    if (tag === "BR") {
      runs.push({ ...fmt, text: " " });
      return;
    }
    if (node.classList?.contains("mk")) return; // a list marker, kept separately
    const f = { ...fmt };
    if (tag === "B" || tag === "STRONG") f.bold = true;
    if (tag === "I" || tag === "EM") f.italic = true;
    if (tag === "U") f.underline = true;
    if (tag === "S" || tag === "STRIKE" || tag === "DEL") f.strike = true;
    if (tag === "SUP") f.superscript = true;
    if (tag === "SUB") f.subscript = true;
    const st = node.style;
    if (st) {
      if (st.fontWeight === "bold" || Number(st.fontWeight) >= 600) f.bold = true;
      if (st.fontStyle === "italic") f.italic = true;
      const deco = st.textDecorationLine || st.textDecoration || "";
      if (deco.includes("underline")) f.underline = true;
      if (deco.includes("line-through")) f.strike = true;
      const c = toHex(st.color);
      if (c) f.color = c;
    }
    if (tag === "FONT" && node.getAttribute("color")) f.color = toHex(node.getAttribute("color")) || f.color;
    // Block-level children (Chrome inserts <div> on Enter) become spaces.
    if ((tag === "DIV" || tag === "P") && runs.length) runs.push({ ...fmt, text: " " });
    node.childNodes.forEach((c) => walk(c, f));
  };
  root.childNodes.forEach((c) => walk(c, {}));
  // Merge neighbours with the same formatting.
  const out = [];
  for (const r of runs) {
    const last = out[out.length - 1];
    if (last && FLAGS.every((k) => !!last[k] === !!r[k]) && (last.color || null) === (r.color || null)) {
      last.text += r.text;
    } else {
      out.push({ ...r });
    }
  }
  if (out.length) {
    out[0].text = out[0].text.replace(/^\s+/, "");
    out[out.length - 1].text = out[out.length - 1].text.replace(/\s+$/, "");
  }
  return out
    .filter((r) => r.text)
    .map((r) => ({
      text: r.text,
      bold: !!r.bold,
      italic: !!r.italic,
      underline: !!r.underline,
      strike: !!r.strike,
      superscript: !!r.superscript,
      subscript: !!r.subscript,
      color: r.color || null,
    }));
}
