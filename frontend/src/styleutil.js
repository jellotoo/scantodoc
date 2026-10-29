// Reading and writing nested style options ("fonts.body.latin").

export function getPath(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

export function setPath(obj, path, value) {
  const keys = path.split(".");
  const copy = Array.isArray(obj) ? [...obj] : { ...obj };
  let cur = copy;
  keys.forEach((k, i) => {
    if (i === keys.length - 1) {
      if (value === undefined) delete cur[k];
      else cur[k] = value;
    } else {
      cur[k] = cur[k] && typeof cur[k] === "object" ? { ...cur[k] } : {};
      cur = cur[k];
    }
  });
  return copy;
}

export const ELEMENTS = [
  ["body", "Body text"],
  ["h1", "Heading 1"],
  ["h2", "Heading 2"],
  ["h3", "Heading 3"],
  ["h4", "Heading 4"],
  ["list", "Lists"],
  ["table", "Tables"],
  ["caption", "Captions"],
  ["footnote", "Footnotes"],
  ["quote", "Quotes"],
];

export const BLOCK_CHOICES = [
  ["paragraph", "Paragraph"],
  ["heading:1", "Heading 1"],
  ["heading:2", "Heading 2"],
  ["heading:3", "Heading 3"],
  ["heading:4", "Heading 4"],
  ["list_item", "List item"],
  ["quote", "Quote"],
  ["caption", "Caption"],
  ["footnote", "Footnote"],
  ["header", "Running head"],
  ["footer", "Running foot"],
  ["page_number", "Page number"],
];

export function blockChoice(block) {
  if (!block) return "";
  return block.type === "heading" ? `heading:${Math.min(Math.max(block.level || 1, 1), 4)}` : block.type;
}

export const TYPE_COLORS = {
  heading: "#6366f1",
  paragraph: "#0ea5e9",
  list_item: "#10b981",
  table: "#f59e0b",
  figure: "#ec4899",
  caption: "#a855f7",
  footnote: "#64748b",
  quote: "#14b8a6",
  header: "#94a3b8",
  footer: "#94a3b8",
  page_number: "#94a3b8",
};
