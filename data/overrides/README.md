# Overrides

Facts no scraped source represents, asserted by hand with a citation.

This is **not** a seventh data source. A scraped source is re-run, maintained,
and can break; an override is a small set of static assertions whose cost is
proportional to how often the underlying facts change. Pick forfeiture is rare
and slow-moving, which is the profile that suits this rather than a scraper.

## Rules for adding a row

1. **A citation URL is required.** Preferably a primary source -- a league
   announcement rather than a write-up of one.
2. **One row per fact.** No ranges, no wildcards. Five forfeited picks are five
   rows, so each is individually reviewable.
3. **Only facts no source carries.** If a scraper could pick it up, fix the
   scraper instead. An override that duplicates scraped data will silently
   diverge from it.
4. **Identify the pick by origin *and* owner.** "The Indiana 2029 first" also
   describes Indiana's own pick. Matching on origin alone forfeited three picks
   that should have been untouched, including one belonging to another team.
5. Overrides are applied *after* scraped data during ingest and are reported in
   the ingest summary, so a correction is visible rather than blended in. An
   override matching nothing is reported too -- that usually means the scraped
   data changed shape and the assertion now points at nothing.

## `pick_overrides.csv`

| Column | Meaning |
|---|---|
| `year`, `round`, `original_team`, `owner_team` | Identifies the pick |
| `action` | `forfeit` is the only action currently supported |
| `citation_url` | Primary source |
| `note` | Why |
| `asserted_on` | When this row was added |

### Why this file exists

The NBA forfeited five Clippers first-round picks (2029–2033) in September 2026
for salary cap circumvention. **No source we scrape represents forfeiture.**
Fanspo models pick ownership and trades only -- verified by re-scraping 24 days
after the penalty, which returned fresh data (`updatedAt` one day old) still
showing LAC holding all five. SalarySwish shows some of those years absent with
no explanation, which is indistinguishable from a trade.

RealGM does distinguish forfeited from traded, but its `robots.txt` carries
`User-agent: anthropic-ai / Disallow: /`, so it is not available to this project
programmatically and is used here only as a human-read reference.

In 2029 the forfeited pick is the **Indiana** first the Clippers held, not their
own; in 2030-2033 it is their own. RealGM's per-year counts (1/0/1/0/1) only
reconcile that way.

**The forfeitures do not leave the Clippers pickless.** They still hold other
teams' firsts in 2029, 2031 and 2033, so the bare years are 2028, 2030 and 2032
-- non-consecutive, and therefore Stepien-legal. That distinction is why this
file marks specific picks rather than blanking whole years.
