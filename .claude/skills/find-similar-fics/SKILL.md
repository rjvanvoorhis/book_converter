---
name: find-similar-fics
description: Find new AO3 fic recommendations by analyzing the stories the user has liked (data/texts/) for craft/voice/structure, then searching AO3 broadly — not limited to a single fandom or tag — and screening candidates for quality per Sturgeon's Law (90% is crud; find the rest). Use when the user asks for fic recommendations, "more like X", or to find good fic beyond their usual tags.
---

Orchestrates two subagents — `taste-profiler` and `fic-scout` — to go from "here are stories I like" (`data/texts/`) to a screened list of new AO3 recommendations. The point of this skill is explicitly to cast a **wider** net than fandom/tag search allows: the user may love something they'd never have found by browsing their usual tags (their own example: a WW2 AU of an unrelated fandom). Craft quality is the primary filter; fandom/ship/tags are secondary or ignored entirely unless the user asks to scope by them.

## When invoked

1. **Check for a taste profile.** Look for `data/taste-profile.md`. `data/texts/` is a staging area — stories can be pulled in before they're read, and only get flagged `good`/`bad` (with an optional note) later via the UI's review modal, which writes a `review.json` next to each story's `book.json`. If the profile is missing, or the newest `review.json` under `data/texts/` is more recent than the profile's "Generated <date>" line (or the user says they've reviewed more stories since), run the `taste-profiler` agent first (foreground — everything downstream depends on its output) before doing anything else.
   Separately, `data/taste-profiles/` (plural) holds standalone case-study files — sharper, single-topic distinctions that don't require a full re-profile to add (see `taste-profiler`'s instructions for the convention). `fic-scout` reads all of them directly every run regardless of the main profile's freshness, so a new case study is picked up immediately without needing this step — only fall back to a full `taste-profiler` run if `data/taste-profile.md`'s case-studies index looks out of date against what's actually in the folder.

2. **Establish search parameters.** Use sensible defaults rather than interrogating the user, per the mechanical filters they've said they care about (word count in particular). Defaults if unstated:
   - Word count: minimum ~15,000-20,000 words (filters out drabbles/one-scene pieces; adjust if the user's liked corpus skews shorter/longer per the taste profile's "Mechanical signal" section)
   - No fandom/ship restriction by default — wide net is the explicit goal
   - Completed works preferred, but don't hard-exclude strong WIPs unless the user says so
   - English language
   - ~8-12 final recommendations, sampled from a pool of ~40-80 candidates
   Only stop to ask the user (via AskUserQuestion) when a choice materially changes the search and isn't inferable — e.g. whether to include a specific fandom they mentioned, or an explicit content rating boundary. Don't ask about things you can default sensibly.

3. **Dispatch `fic-scout`.** For breadth without redundant work, consider launching 2-3 `fic-scout` agents in parallel (in the background) with different search angles — e.g. different sort orders (kudos vs. recency), different word-count bands, or a couple of distinct query-term seeds — rather than one agent grinding a single query. Each needs: the taste profile path, the mechanical filters, and its specific search angle. A single agent is fine for a narrower/quick ask.

4. **Merge and present results.** Once scout(s) report back, deduplicate by AO3 work id, keep only the candidates that actually scored well (don't pad to hit a target count), and present a ranked list to the user with title/author/link/word count/why-it-matches. Save the final list to `data/fic-recommendations/<yyyy-mm-dd>.md` so it persists across sessions, and mention that path to the user.

5. **Iterate on request.** If the user wants more, narrower, or differently-angled results (e.g. "only gen, no romance" or "try angsty stuff specifically"), re-dispatch `fic-scout` with adjusted parameters rather than re-running `taste-profiler` (the taste profile doesn't change unless the liked-stories corpus does).

## Notes

- This is inherently a judgment task, not a mechanical filter — the value is in `fic-scout` actually reading prose samples against the taste profile, not just sorting by kudos. Resist the urge to shortcut this by returning popular/highly-kudos'd works unread.
- AO3 content behind login (some mature/explicit or restricted works) is reachable if an account is configured in the gitignored `ao3_credentials.json` at the repo root, otherwise it isn't. Scouts can't tell from their end whether credentials are configured, so they'll note any login-walled fetch failure rather than silently dropping it — surface that to the user too if it seems to be excluding a meaningful chunk of relevant results.
- If the user's ask names a specific narrower scope up front ("more slow-burn like Icarus" or "just AO3 fic under the Avatar tag but not one I'd normally find"), pass that through as a fic-scout parameter rather than defaulting to fully wide-open.
