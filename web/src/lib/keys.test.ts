import { describe, it, expect } from "vitest"
import { isCmdK } from "./keys"

describe("isCmdK (⌘K / Ctrl+K command-field shortcut)", () => {
  it("is true for Cmd+K (mac)", () => {
    expect(isCmdK({ metaKey: true, ctrlKey: false, key: "k" })).toBe(true)
  })

  it("is true for Ctrl+K (win/linux)", () => {
    expect(isCmdK({ metaKey: false, ctrlKey: true, key: "k" })).toBe(true)
  })

  it("is case-insensitive on the key (Shift may upcase it)", () => {
    expect(isCmdK({ metaKey: true, ctrlKey: false, key: "K" })).toBe(true)
  })

  it("is false for a bare 'k' with no modifier", () => {
    expect(isCmdK({ metaKey: false, ctrlKey: false, key: "k" })).toBe(false)
  })

  it("is false for a modifier with the wrong key", () => {
    expect(isCmdK({ metaKey: true, ctrlKey: false, key: "j" })).toBe(false)
  })

  it("is false for Shift/Alt variants (don't hijack Ctrl+Shift+K devtools)", () => {
    expect(isCmdK({ metaKey: false, ctrlKey: true, key: "k", shiftKey: true })).toBe(false)
    expect(isCmdK({ metaKey: true, ctrlKey: false, key: "k", altKey: true })).toBe(false)
  })
})
