/** The Ask page owns a full-width corpus search input, so the global nav "Ask the corpus… ⌘K"
    command field is redundant (and overlaps it on mobile) while on /ask. One canonical input:
    hide the nav command field on the Ask route. ⌘K still navigates to /ask from elsewhere. */
export function shouldShowNavSearch(pathname: string): boolean {
  return !pathname.startsWith("/ask")
}
