// WCAG 2.x relative luminance and contrast ratio, for the token gate and for
// picking readable ink on arbitrary team colours at runtime.

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex: string): number {
  const n = parseInt(hex.replace("#", ""), 16);
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Dark or light ink, whichever reads better on `background`. */
export function inkFor(background: string, dark = "#0B0D10", light = "#F3F5F8"): string {
  return contrast(dark, background) >= contrast(light, background) ? dark : light;
}
