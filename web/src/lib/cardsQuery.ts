/**
 * Cards search input state (BACKLOG P4 #11).
 *
 * A single source of truth for the query box so the *visible* input and the *internal* state can
 * never diverge — the defect where selecting a suggestion chip left hidden state behind and later
 * text appended to stale content. `question` is the one value bound to the input; `submitted` is
 * the query that produced the currently-shown results and is always *derived* from `question`.
 */
export interface CardsQueryState {
  /** Bound to the input's `value` AND the single source of truth for the query text. */
  question: string
  /** The query that produced the displayed results; null before the first search. */
  submitted: string | null
}

export const initialCardsQuery: CardsQueryState = { question: "", submitted: null }

export type CardsQueryAction =
  | { type: "type"; text: string } // user typed — always replaces (never appends to stale text)
  | { type: "selectChip"; text: string } // suggestion chip — its text becomes the visible input
  | { type: "clear" }
  | { type: "submit" } // freeze the current question as the submitted query (derived, trimmed)

export function cardsQueryReducer(
  state: CardsQueryState,
  action: CardsQueryAction,
): CardsQueryState {
  switch (action.type) {
    case "type":
      // Typing replaces the whole value — the input is controlled, so what the user sees IS the
      // state. No appending onto a chip's hidden text.
      return { ...state, question: action.text }
    case "selectChip":
      // The chip's text becomes the visible input, keeping input and state identical.
      return { ...state, question: action.text }
    case "clear":
      return { ...state, question: "" }
    case "submit":
      // submitted is always derived from the current (visible) question — they cannot diverge.
      return { ...state, submitted: state.question.trim() }
    default:
      return state
  }
}
