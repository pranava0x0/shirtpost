// Merch variety options (TRENDS-DISCOVERY-SPEC Part C). Layout ids mirror
// backend factory/layouts.LAYOUTS. Kept here (not inline in TrendCard) per the
// frontend constants rule.
//
// Per-drop garment color is intentionally NOT offered here: changing the ink
// without also changing the ordered Printful variant prints (e.g.) dark ink on
// the default black shirt — an invisible print. Real garment variety needs a
// Printful color->variant map (owner-supplied catalog ids); see backlog.md.

export const LAYOUT_OPTIONS: { value: string; label: string }[] = [
  { value: "centered", label: "Centered stack" },
  { value: "top_left", label: "Left chest" },
  { value: "oversized", label: "Oversized lowercase" },
  { value: "boxed", label: "Boxed outline" },
];
