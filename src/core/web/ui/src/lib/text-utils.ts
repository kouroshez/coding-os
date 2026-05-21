/**
 * Simple text utility to check if the text contains RTL characters
 * (like Persian, Arabic, or Hebrew).
 */
export function isRTL(text?: string | null): boolean {
  if (!text) return false;
  // Persian/Arabic Unicode range is \u0600-\u06FF
  const rtlRegex = /[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u0590-\u05FF]/;
  return rtlRegex.test(text);
}
