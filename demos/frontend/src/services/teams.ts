/**
 * Microsoft Teams integration helpers.
 * Detects if the app is running inside a Teams tab (iframe)
 * and provides context/theme information.
 */
import { app, pages } from '@microsoft/teams-js';

let _initialized = false;
let _inTeams = false;
let _context: app.Context | null = null;

/**
 * Initialize the Teams SDK. Safe to call outside Teams — will
 * detect the environment and set _inTeams accordingly.
 */
export async function initializeTeams(): Promise<boolean> {
  if (_initialized) return _inTeams;
  
  try {
    await app.initialize();
    _inTeams = true;
    _context = await app.getContext();
    
    // Notify Teams that the tab content is ready
    app.notifySuccess();
    
    _initialized = true;
    return true;
  } catch {
    // Not running in Teams — that's fine
    _inTeams = false;
    _initialized = true;
    return false;
  }
}

/** Returns true if the app is running inside a Teams tab. */
export function isInTeams(): boolean {
  return _inTeams;
}

/** Get the Teams context (theme, locale, user, etc.). */
export function getTeamsContext(): app.Context | null {
  return _context;
}

/**
 * Get the current Teams theme name.
 * Returns 'default' (light), 'dark', or 'contrast'.
 * Falls back to 'default' when not in Teams.
 */
export function getTeamsTheme(): string {
  return _context?.app?.theme ?? 'default';
}

/**
 * Register a callback for Teams theme changes.
 */
export function onTeamsThemeChange(callback: (theme: string) => void): void {
  if (_inTeams) {
    app.registerOnThemeChangeHandler(callback);
  }
}

/** Maps a Teams theme name onto the `data-theme` token overrides (styles/tokens.css). */
export function applyTeamsThemeToDocument(theme: string): void {
  const root = document.documentElement;
  if (theme === 'dark') root.dataset.theme = 'teams-dark';
  else if (theme === 'contrast') root.dataset.theme = 'teams-contrast';
  else delete root.dataset.theme;
}

/**
 * Initializes Teams once and keeps the document theme in sync with the host.
 * Outside Teams this resolves to `false` and leaves the default light theme.
 */
export async function syncDocumentThemeWithTeams(): Promise<boolean> {
  const inTeams = await initializeTeams();
  if (!inTeams) return false;
  applyTeamsThemeToDocument(getTeamsTheme());
  onTeamsThemeChange(applyTeamsThemeToDocument);
  return true;
}
