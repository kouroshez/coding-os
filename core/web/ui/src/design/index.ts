/**
 * Design system public surface.
 *
 * PURPOSE: Single import point for theme types, provider, and hook.
 *          Consumed by every feature (board, graph, search, cognition)
 *          plus the Hub shell.
 * NOTES:   Token CSS is still loaded globally via index.html;
 *          only the TS/React integration lives here.
 */
export { DesignThemeProvider, useDesignTheme } from './ThemeProvider';
export type { FeatureShell } from './ThemeProvider';
export {
  DEFAULT_DESIGN_TWEAKS,
  type Aesthetic,
  type Density,
  type DesignTweaks,
  type Theme,
} from './types';
