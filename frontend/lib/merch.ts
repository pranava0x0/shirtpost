// Merch variety options (TRENDS-DISCOVERY-SPEC Part C). Layout ids mirror
// backend factory/render.LAYOUTS; garment names mirror printful._GARMENT_HEX.
// Kept here (not inline in TrendCard) per the frontend constants rule.

export const LAYOUT_OPTIONS: { value: string; label: string }[] = [
  { value: "centered", label: "Centered stack" },
  { value: "top_left", label: "Left chest" },
  { value: "oversized", label: "Oversized lowercase" },
  { value: "boxed", label: "Boxed outline" },
];

// name = the value sent to the backend; swatch = an approximate CSS color for the
// dropdown chip. Ink auto-contrasts server-side, so only the garment is chosen.
export const GARMENT_OPTIONS: { value: string; label: string; swatch: string }[] = [
  { value: "black", label: "Black", swatch: "#000000" },
  { value: "white", label: "White", swatch: "#FFFFFF" },
  { value: "navy", label: "Navy", swatch: "#1F2A44" },
  { value: "sport grey", label: "Sport grey", swatch: "#B4B4B4" },
  { value: "maroon", label: "Maroon", swatch: "#5C1A1B" },
];

export const DEFAULT_LAYOUT = "centered";
export const DEFAULT_GARMENT = "black";
