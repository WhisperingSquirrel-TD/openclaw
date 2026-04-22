# AI Briefing Policy

Version: 1.0
Owner: Tom Dean (via L1)
Applied by: `rank.py` (heuristic pre-filter + Haiku scoring)

---

## Purpose

This policy defines what belongs in a weekly AI briefing for Tom Dean, an independent AI
consultant. The audience is one person — Tom — and the standard is: would this change how he
advises clients, spots opportunities, or thinks about the field? If no, it doesn't belong.

---

## Inclusion criteria

An item is a candidate if it meets **at least one** of the following:

1. **Model capability jump** — a meaningfully new model (not a point release) that changes
   what's possible for enterprise clients (context, reasoning, multimodal, cost, speed).

2. **Enterprise AI adoption signal** — a major company deploying AI in a way that illustrates
   a pattern Tom's clients should know about (what worked, what failed, what was unexpected).

3. **Agent/tooling development** — a meaningful change to the agent or tooling layer that
   affects how AI systems are built or operated at scale (frameworks, orchestration, evals,
   observability, memory, RAG patterns).

4. **Pricing or economics shift** — a model pricing change, API cost restructure, or open
   weight release that materially changes the build-vs-buy calculus for clients.

5. **Governance or compliance** — a regulation, standard, or major policy announcement that
   affects what clients can deploy, how, or where (EU AI Act implementation, sector-specific
   rules, liability precedents).

6. **Failure or risk signal** — a documented deployment failure, safety incident, or legal
   action that reveals a risk Tom should flag to clients considering similar paths.

---

## Exclusion criteria (hard filters — remove before scoring)

Remove an item if **any** of the following apply:

- Consumer product news with no enterprise implication (new chatbot UI, consumer app launch)
- Pure research paper with no near-term deployment path
- Speculative rumour or unverified leak
- Already covered in a previous briefing (item in `included-items.json`)
- Duplicated across multiple sources without new information (collapse to one entry)
- Published more than 14 days ago (outside lookback window)
- Opinion / commentary piece without underlying news event
- Marketing content from a vendor (product blogs, press releases dressed as news)

---

## Scoring dimensions (used by Haiku)

Rate each candidate 1–5 on each dimension. Items with total score ≥ 10 are shortlisted.

| Dimension | 1 | 5 |
|-----------|---|---|
| **Relevance** | Tangential to AI consulting | Core to how AI is built and deployed for enterprise |
| **Novelty** | Well-known already | Genuinely new information Tom is unlikely to have seen |
| **Actionability** | Nothing to think or say differently | Clear implication for client advice or opportunity spotting |
| **Credibility** | Unverified, speculative | Confirmed, from a primary source |

**Total ≥ 10 of 20 → shortlist candidate**
**Total ≥ 14 of 20 → priority candidate (Tavily enrichment eligible)**

---

## Output format contract

Every item in the final briefing must include:

```
### [n]. <Title>
**Source:** <publication> · <date>
**Category:** <one of: model-capability | enterprise-adoption | agent-tooling | economics | governance | risk>
**What changed:** <1–2 sentences — the news itself>
**Why it matters:** <1–2 sentences — consulting implication>
**What to think or say differently:** <1–3 bullet points — concrete changes to Tom's advice or framing>
```

---

## "Nothing important" threshold

If fewer than 2 candidates score ≥ 10 after filtering, produce a "quiet week" briefing:
- List any watch-items (score 7–9) with title + source + 1-line note
- Include the explicit statement: "Nothing materially important this week."
- Do not force filler items to meet the threshold

---

## Source weighting

Feeds are weighted in `ai-briefing-sources.yaml`. Higher-weight sources are harder to filter
out during heuristic pre-filtering. Weight does not override the exclusion criteria.

| Weight | Meaning |
|--------|---------|
| 1.0 | Highest signal — primary research or practitioner sources |
| 0.8 | Strong signal — major trade press with good editorial quality |
| 0.6 | Moderate signal — general tech press, good coverage but more noise |
| 0.4 | Lower signal — aggregators, newsletters, higher volume |
