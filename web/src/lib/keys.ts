/**
 * keys — pure keyboard-shortcut predicates (no React import).
 *
 * Kept here so the NavBar's ⌘K listener stays a one-liner and the matching
 * logic is unit-testable in isolation (react-refresh/only-export-components safe).
 */

/** True for the PLAIN Cmd+K (mac) / Ctrl+K (win/linux) command-field shortcut, case-insensitive.
    Excludes Shift/Alt variants so we don't hijack browser combos like Ctrl+Shift+K (devtools). */
export function isCmdK(e: {
  metaKey: boolean
  ctrlKey: boolean
  key: string
  shiftKey?: boolean
  altKey?: boolean
}): boolean {
  return (e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "k"
}
