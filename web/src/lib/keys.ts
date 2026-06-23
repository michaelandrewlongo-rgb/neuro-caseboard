/**
 * keys — pure keyboard-shortcut predicates (no React import).
 *
 * Kept here so the NavBar's ⌘K listener stays a one-liner and the matching
 * logic is unit-testable in isolation (react-refresh/only-export-components safe).
 */

/** True for the Cmd+K (mac) / Ctrl+K (win/linux) command-field shortcut, case-insensitive. */
export function isCmdK(e: { metaKey: boolean; ctrlKey: boolean; key: string }): boolean {
  return (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k"
}
