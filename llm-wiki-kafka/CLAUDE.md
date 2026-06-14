# LLM Wiki Schema — INSY 695 Knowledge Base

This is an LLM-maintained wiki over the course materials for **INSY 695 — Enterprise Data Science & ML in Production II** (McGill Desautels, instructor Fatih Nayebi). It follows [Andrej Karpathy's LLM Wiki pattern](../karpathy-llm-wiki.md).

Owner: Othmane Zizi (McGill MMA). The wiki is the codebase; the LLM is the programmer; Obsidian is the IDE.

## Layers

- **Raw sources** — `../markdown/*.md` (converted from `../raw/*.pdf` with markitdown). Immutable. Read, never edit.
- **The wiki** — this directory. LLM-owned and maintained.
- **The schema** — this file.

## Directory layout

- `index.md` — catalog of every page (content-oriented). Update on every ingest.
- `log.md` — append-only chronological record. Prefix entries `## [YYYY-MM-DD] ingest|query|lint | Title`.
- `overview.md` — the synthesis / through-line of the whole course.
- `sources/` — one summary page per raw document.
- `concepts/` — cross-cutting themes that span multiple sources (the synthesis layer).
- `entities/` — named tools, systems, algorithms, and theorems (the nouns).

## Conventions

- **Links use Obsidian wikilinks**: `[[apache-kafka]]` or `[[apache-kafka|Apache Kafka]]`. Filenames are unique kebab-case so links resolve across folders and the graph view renders connections.
- **Every page links liberally.** Source pages link to the entities/concepts they cover; concept pages link to their sources and entities; entity pages link back to concepts and to related entities.
- **Source pages** contain: one-line summary, key takeaways (bullets), and a "Connects to" section of links.
- **Entity pages** are concise (a few sentences + links): what it is, why it matters here, where it appears.
- **Concept pages** synthesize across sources with citations as wikilinks.
- A wikilink to a page that doesn't exist yet is fine — it marks a page worth creating.

## Operations

- **Ingest** a new source: read it, write `sources/<slug>.md`, update/create relevant `concepts/` and `entities/` pages, update `index.md`, append to `log.md`.
- **Query**: read `index.md`, drill into relevant pages, synthesize with wikilink citations. File good answers back as new `concepts/` pages.
- **Lint**: check for contradictions, orphan pages, missing concept pages, stale claims, and gaps fillable by web search.

## Domain note

The corpus is course lecture decks (slide-derived, so terse) plus a syllabus and two cheat sheets. The live artifact tying it together is the **[[kafka-spark-assignment]]** (Individual Assignment 1: generate an event stream in Kafka/Confluent, process it in Spark/Databricks). Streaming concepts in the wiki are the theory behind that assignment.
