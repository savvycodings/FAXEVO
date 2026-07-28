# Guide

Codebase walkthrough docs for the Xevo mobile app — dev-focused, screen → route → DB.

| Doc | Contents |
|-----|----------|
| [01-screens-routes-db.md](./01-screens-routes-db.md) | Bottom tabs, shared session layer, stack screens, mermaid maps |
| [02-correction-images.md](./02-correction-images.md) | Correction image pipeline — pose pick → deltas → Comfy → cache |
| [03-mesh-retrieval.md](./03-mesh-retrieval.md) | Mesh / k-NN shot matching — Modal → pose_enrichment → pgvector → retrieval bench |
| [04-gamification.md](./04-gamification.md) | Gamification catalog — XP, levels/tiers, achievements, daily/weekly/season quests, leaderboard |
| [../SENIOR-DEV-HANDOFF-PACKAGE.md](../SENIOR-DEV-HANDOFF-PACKAGE.md) | Senior dev handoff — start here for validation package |
| [../SHOT-SYSTEM-VALIDATION-HANDOVER.md](../SHOT-SYSTEM-VALIDATION-HANDOVER.md) | Shot retrieval validation — verdict, false positives, scaling |
| [../TRAIN-DATA-CURATION-GUIDE.md](../TRAIN-DATA-CURATION-GUIDE.md) | Pro training video selection (torso-normalized pose) |
| [../PER-LABEL-TEST-CHECKLIST.md](../PER-LABEL-TEST-CHECKLIST.md) | Per-label smoke + generalization test steps |
| [../SHOT-E2E-VALIDATION-SESSION.md](../SHOT-E2E-VALIDATION-SESSION.md) | E2E session detail — Neon + bench results |

Later volumes: per-page component trees, analyze sequence, full `metrics` schema.
