# How It Works — and How to Build Your Own

*A plain-language guide for residents in any specialty.*

This document explains what this tool does, how it works under the hood, and what
it would take for you to build your own version from the textbooks you already
own. No programming background is assumed. Every technical term is explained the
first time it appears.

> **One thing up front:** this is a personal study and reference aid. It is
> decision-support, not a substitute for your own clinical judgment, and nothing
> here is legal advice.

---

## What is this?

This is a private question-and-answer tool that runs on your own computer and
answers clinical questions using *only* the textbooks you feed it. You ask
something in plain English — "What is the normal range for intracranial pressure
in adults?" — and it writes back a short, direct answer in which **every claim is
tagged with exactly where it came from**: which book, which chapter, which page.
If the answer isn't in your books, it says so ("Not found in the provided
sources.") rather than guessing. If two of your books disagree, it tells you they
disagree and shows you each side. For anatomy or imaging questions, it can also
pull up the actual figure or atlas plate from the page and show it to you.

The whole thing was built by a neurosurgery resident for his own studying, but
**nothing about it is specific to neurosurgery.** Point it at a folder of
cardiology, dermatology, or pathology PDFs and it becomes a grounded reference
tool for that field instead.

---

## An everyday analogy

Imagine hiring a tireless research librarian who has read every book on *your*
shelf — and only your shelf. When you ask a question, this librarian doesn't
recite from memory or make things up. They walk to the stacks, find the handful
of passages that actually address your question, lay them on the desk, and write
you a tight summary — and beside every sentence they jot the exact page they took
it from. If your books don't cover it, they tell you plainly: "It's not in here."
They never invent a source, and they never quote a book you don't own.

That is what this tool is: a librarian for the books *you* legally have, who
always shows their work.

---

## What happens when you ask a question

Behind the scenes there are two phases. The first is a **one-time setup** that
happens before you ask anything; the second runs each time you ask.

### Phase one: getting your books ready (done once)

Before you can ask anything, the tool has to read and organize your books. This
is called **building the index** — think of it as the librarian reading every
book once and writing a detailed card catalog.

1. **It reads each PDF and pulls out the text.** It also reads each book's table
   of contents, so it knows which chapter every page belongs to. (This is why
   citations can say a real chapter name, not just a page number.)

2. **It cuts the text into bite-sized passages.** A whole chapter is too big to
   work with, so the text is sliced into small overlapping chunks of roughly a
   few hundred words each. The overlap means a sentence that falls on a boundary
   isn't lost.

3. **It gives each passage a "meaning fingerprint."** For every chunk, the tool
   computes an **embedding** — a list of numbers that captures what the passage
   is *about*, so that passages with similar meaning end up with similar numbers.
   This is what later lets it find relevant text even when your question uses
   different words than the book does.

4. **It spots and saves the figures.** As it goes, it notices pages that are
   mostly image — atlas plates, radiology figures — and saves a picture of each
   such page so it can show them to you later.

All of this is stored privately on your computer in a searchable **index** (a
catalog the tool can look things up in quickly). This step takes a while — minutes
if your computer has a graphics card, around an hour if it doesn't (more on that
below) — but you only do it once, and only redo it when you add or change books.

### Phase two: answering your question (every time)

5. **It searches your books two different ways at once.** This matters, so here
   are both:
   - **By meaning:** it turns your question into the same kind of "meaning
     fingerprint" and finds passages whose meaning is closest. This catches the
     right content even when your wording differs from the book's.
   - **By exact keywords:** it also does an old-fashioned word match. This is what
     reliably catches specific drug names, eponyms (Cushing, Glasgow), and scale
     names — terms where the *exact* word matters.

6. **It merges the two result lists.** Each search returns its own ranked list of
   candidate passages; the tool blends them into one combined shortlist, so a
   passage that scored well on *either* method rises. (Using both meaning and
   keywords together is called **hybrid search**.)

7. **It re-ranks the shortlist to find the true best few.** A more careful
   (and slower) step called **reranking** re-examines each candidate against your
   exact question and reorders them, so the genuinely most relevant passages float
   to the top. Only the best six are kept. This is the key to a clean answer: the
   final writer sees six strong passages instead of twenty noisy ones.

8. **For visual questions, it also gathers the matching figures.** In parallel
   with the text search, a separate "visual" lane looks for figure pages whose
   *image* best matches your question — useful for pure atlas plates that have
   little caption text. The best figure pages from both lanes are combined and a
   small number are set aside to show you.

9. **Only now does anything leave your computer.** The tool hands those few best
   passages — plus your question, and for visual questions the matched figure
   page images — to a cloud **AI model** (a large language model, the kind of
   system that can read text and write fluent answers). The model is given strict
   instructions: answer *only* from the passages provided, cite a source number
   for every claim, say "Not found in the provided sources." if the passages don't
   cover it, and call out any disagreement between sources.

10. **You get a cited answer.** The answer comes back with numbered citations, a
    list of the sources (book → chapter → page), and, when relevant, the figure
    images shown inline. If the model couldn't find the answer in your passages,
    it returns the "Not found" message and shows **no** sources and **no** figures
    — so a refusal never comes dressed up with citations that don't actually
    support it.

You can read these answers either in a simple command window or in a small page
in your web browser that runs entirely on your own machine and shows the figures
properly.

---

## Why your books stay safe

This is the heart of the design, so it's worth being precise about it.

**Your textbook PDFs never leave your computer.** The reading, the chunking, the
meaning-fingerprints, the figure images, and the searchable index are all created
and stored locally. They are never uploaded anywhere.

**The only thing that ever leaves your machine** is what's needed for that final
answer-writing step: your question, the small handful of relevant excerpts the
search surfaced (six passages, not chapters or books), and — for picture
questions only — the images of the specific figure pages that matched. **The
whole books are never sent. The index is never sent. Nothing is ever
redistributed or shared with other users.**

Why this matters for copyright: you are not copying or republishing anyone's
textbook. You start from books you **legally obtained**, you build a **private**
tool for **your own use**, and the only material that travels is the same kind of
brief excerpt you might quote when looking something up. Each person who wants
this builds their own copy from their own books — there is no shared library, no
central server handing out copyrighted content.

Two honest caveats, because this should not be overstated:
- For visual questions, the excerpt that's sent is an *image of a textbook page*.
  That's a larger piece of the book than a few sentences of text, so factor that
  in when you choose which cloud provider to use and how comfortable you are
  sending it.
- This is a description of how the tool is built, not legal advice. It is designed
  for personal, local use. If you have institutional rules or licensing terms that
  govern your textbooks, those still apply.

---

## Could I build one for my specialty?

Yes — and you don't need to be technical to do it. Here is an honest picture of
what it takes.

**What you need:**

- **Your own textbook PDFs, with real text.** This is the most important
  requirement. The PDF must contain *selectable* text — if you can highlight and
  copy a sentence in a normal PDF reader, you're fine. A PDF that is just *scanned
  photographs* of pages (where the text is really a picture) will not work,
  because this tool reads text and does not do OCR (optical character recognition,
  the technology that converts a photo of text into actual text). Most
  professionally published e-textbooks have a real text layer.

- **A reasonably capable personal computer.** A gaming-style PC with an **NVIDIA
  graphics card** (a **GPU** — a chip that does many calculations at once) is
  ideal: it builds the index in minutes. It is *not* strictly required — a normal
  computer works too — but without a GPU the one-time setup takes around an hour,
  and each question takes a bit longer to start up. The questions themselves are
  cheap to run either way.

- **A free or low-cost cloud AI account.** Only the final answer-writing step
  uses the cloud. By default the tool uses Google's Vertex AI Gemini, which means
  a Google Cloud account; an alternative service (OpenRouter) is also supported if
  you prefer. Costs are modest for personal use, but they depend on the model you
  pick and whether your question pulls in figure images (images cost more than
  text). Check your provider's current pricing; choosing a lighter model (for
  example Gemini's faster "flash" tier instead of "pro") cuts the cost
  substantially. It is not zero, and it requires internet for that one step.

- **A willingness to follow setup steps once.** You install the software, point it
  at your folder of PDFs, sign in to your cloud account, and build the index. It's
  a one-time, follow-the-recipe effort. The exact commands live in the project's
  `README.md`; this document deliberately keeps things conceptual so you
  understand *what* each step does rather than memorizing *how* to type it.

**Realistic effort level:** if you can install an app and follow written
instructions, you can stand this up in an afternoon. The thinking part — deciding
which books to include — is the part only you can do.

---

## What it's good at, and what it can't do

**It's good at:**

- Answering on-the-job factual questions from *your* trusted books, fast.
- Showing its work — every claim is tied to book, chapter, and page, so you can
  verify it yourself.
- Saying "I don't know" honestly when your books don't cover something, instead of
  confidently making something up.
- Flagging when your own sources disagree, rather than silently picking one.
- Pulling up the relevant atlas plate or figure for anatomy and imaging questions.

**It can't (and won't):**

- **Read scanned-image PDFs.** No real text layer means no usable content.
- **Know anything outside the books you give it.** It is only as good and as
  current as your bookshelf. It does not browse the internet for medical facts.
- **Replace clinical judgment.** It is a study and reference aid. Treat its
  answers the way you'd treat a quick textbook lookup: a starting point you
  confirm, not a final order.
- **Work entirely offline.** The reading and searching are local, but the final
  answer step needs internet and your cloud account.
- **Crop figures tightly.** When it shows a figure, it shows the whole page (so
  the caption travels with the image), not a zoomed-in cut-out.

---

## Mini-glossary

- **RAG (retrieval-augmented generation):** the overall approach used here — first
  *retrieve* the relevant passages from your books, then have an AI *generate* an
  answer grounded in only those passages. It's what keeps the answers tied to your
  sources instead of the AI's general memory.
- **Embedding:** a "meaning fingerprint" — a list of numbers representing what a
  piece of text (or an image) is about, so the tool can find things by meaning,
  not just by exact words.
- **Index:** the private, searchable catalog of your books that the tool builds
  once and then looks things up in quickly.
- **Hybrid search / reranking:** searching by meaning *and* by exact keyword at
  the same time, then carefully reordering the results so the best few rise to the
  top before the AI sees them.
- **GPU (graphics card):** a computer chip that does many calculations at once;
  having one turns the one-time setup from about an hour into a few minutes.
- **API / cloud AI model:** the cloud service that writes the final worded answer.
  "API" just means the standardized way your computer talks to that service over
  the internet. It's the one part that leaves your machine — and it only ever
  receives your question and a few excerpts, never your books.

---

*For the exact installation and setup commands, see the project `README.md`.
This document is the "why and what"; the README is the "how."*
