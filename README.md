# Preski Fitness HQ

Start here. Type **"status"** (or "HQ") in Claude and the main agent gives you one report across every system: what to do today, a red/amber/green board, what changed, and what's blocking you.

## Skills

| Skill | Say | What it does |
|---|---|---|
| `preski-hq` | "status", "HQ", "today" | Main agent. Reports on every system and ranks what to do next. Read-only. |
| `preski-scriptwriter` | "rank these ideas", "batch" | Ranks ideas, writes hooks, picks a winner, full 60s script, caption, pinned comment. |
| `content-library-intelligence` | "find clips of...", "match footage to this script" | Indexes and tags your footage library and finds the right clips. |

## Systems

| Folder | What it is |
|---|---|
| `.claude/skills/preski-hq/` | Main agent: `systems.md` (what it checks), `hq-status.md` (latest report) |
| `.claude/skills/preski-scriptwriter/` | Script writer and `content-bank.md` |
| `.claude/skills/content-library-intelligence/` | Footage library tools |
| `daily-post-v2/` | Daily Post renderer and go-live notes |
| `site-v2/` | New landing page and guides |
| `site/` | Netlify functions: applications, sign-ups, checkout, Stripe webhook |

## Rules
Nothing is published, approved, sent, spent or deleted without your yes. Originals of your footage are never touched.
