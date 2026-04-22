# AI Briefing Sources

Human-readable companion to `ai-briefing-sources.yaml`.

Edit `ai-briefing-sources.yaml` to add/remove/reweight feeds.
This file is for reference and notes only — the pipeline reads the YAML.

---

## Current feed list

### AI Research & Primary Sources (weight 0.8–1.0)

| Source | URL | Notes |
|--------|-----|-------|
| Google DeepMind Blog | https://deepmind.google/blog/rss.xml | Primary research announcements |
| Anthropic News | https://www.anthropic.com/news/rss.json | Model releases, safety, governance |
| OpenAI News | https://openai.com/news/rss/ | Model releases, API, policy |
| Meta AI Blog | https://ai.meta.com/blog/rss/ | Open weights, LLaMA releases |
| Microsoft AI Blog | https://blogs.microsoft.com/ai/feed/ | Enterprise AI, Copilot, Azure |
| Google AI Blog | https://blog.google/technology/ai/rss/ | Gemini, Cloud AI, research |

### Enterprise AI & Industry (weight 0.6–0.8)

| Source | URL | Notes |
|--------|-----|-------|
| MIT Technology Review AI | https://www.technologyreview.com/topic/artificial-intelligence/feed/ | High-quality long-form, good signal |
| The Gradient | https://thegradient.pub/rss/ | Practitioner perspectives, research translation |
| VentureBeat AI | https://venturebeat.com/ai/feed/ | Enterprise deployments, funding, market |
| TechCrunch AI | https://techcrunch.com/category/artificial-intelligence/feed/ | Fast news, funding, product launches |

### Agent Tooling & Practitioner (weight 0.8–1.0)

| Source | URL | Notes |
|--------|-----|-------|
| LangChain Blog | https://blog.langchain.dev/rss/ | Agent frameworks, RAG, production patterns |
| Simon Willison's Weblog | https://simonwillison.net/atom/everything/ | Best independent practitioner commentary |
| Hugging Face Blog | https://huggingface.co/blog/feed.xml | Model releases, open weights, tooling |
| The Register AI | https://www.theregister.com/software/ai_ml/headlines.atom | Enterprise failures, governance, risk |

### Governance & Regulation (weight 0.8)

| Source | URL | Notes |
|--------|-----|-------|
| Future of Life Institute | https://futureoflife.org/feed/ | Policy, safety, risk |
| AI Now Institute | https://ainowinstitute.org/feed | Labour, accountability, policy |

### Economics & Market (weight 0.8–1.0)

| Source | URL | Notes |
|--------|-----|-------|
| Stratechery | https://stratechery.com/feed/ | Deep business analysis — paywalled posts may be stubs |
| Benedict Evans | https://www.ben-evans.com/benedictevans?format=rss | Market structure, enterprise adoption trends |

---

## Adding a new source

1. Open `ai-briefing-sources.yaml`
2. Add an entry with `name`, `url`, `weight`, `category`, `active: true`
3. The pipeline picks it up on the next run automatically

## Pausing a source without deleting it

Set `active: false` in the YAML entry.

## Weight guidance

- **1.0** — Primary source, high signal, rarely produces noise
- **0.8** — Strong trade press or practitioner source with good editorial quality
- **0.6** — Broad tech press — useful but more noise, harder filters applied
- **0.4** — Aggregators or high-volume newsletters (not currently used)
