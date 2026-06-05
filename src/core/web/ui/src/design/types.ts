/**
 * Shared design system types (theme, density, aesthetic, tweaks).
 *
 * PURPOSE: Canonical typed surface consumed by every feature (board,
 *          graph, search, cognition).  Any new aesthetic/density lives
 *          here first, then is implemented in design-tokens.css.
 * NOTES:   Aesthetic/Theme pairs map to `data-aesthetic` + `data-theme`
 *          attributes on <html>, read by the CSS token layer.
 */

export type Theme = 'light' | 'dark';
export type Density = 'cozy' | 'compact';
export type Aesthetic = 'whiteboard' | 'graph' | 'terminal';

export interface DesignTweaks {
  theme: Theme;
  density: Density;
  aesthetic: Aesthetic;
  quietMode: boolean;
}

export const DEFAULT_DESIGN_TWEAKS: DesignTweaks = {
  theme: 'dark',
  density: 'cozy',
  aesthetic: 'whiteboard',
  quietMode: false,
};
