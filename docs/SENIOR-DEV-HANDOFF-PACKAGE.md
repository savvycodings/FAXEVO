# Senior dev handoff package

**Send this page + linked files.** No secrets in docs — rotate `DATABASE_URL` / admin keys before wider sharing.

---

## Start here (5 min read)

[SHOT-SYSTEM-VALIDATION-HANDOVER.md](./SHOT-SYSTEM-VALIDATION-HANDOVER.md)

**One-line status:** Pipeline validated (smoke A/B). One real generalization case (Return, analysis `039a239c`). False positives documented. Scale to 10–20 shots **not** validated — blocked on curated training data + per-label different-file tests.

---

## Attach or link these artifacts

| File | Purpose |
|------|---------|
| [docs/SHOT-SYSTEM-VALIDATION-HANDOVER.md](./SHOT-SYSTEM-VALIDATION-HANDOVER.md) | Verdict, A/B/C, mesh/MP, admin bench, scaling risks |
| [docs/SHOT-E2E-VALIDATION-SESSION.md](./SHOT-E2E-VALIDATION-SESSION.md) | Per-submission detail + repro commands |
| [server/scripts/_e2e_session_investigation.json](../server/scripts/_e2e_session_investigation.json) | Full Neon retrieval metrics |
| [server/scripts/_e2e_bench_results.json](../server/scripts/_e2e_bench_results.json) | Bench steps 1, 2, 5 |
| [server/scripts/_e2e_pose_mesh_compare.json](../server/scripts/_e2e_pose_mesh_compare.json) | Landmarks + pose distance for submission C |

---

## Supporting runbooks (for library growth)

| Doc | When |
|-----|------|
| [TRAIN-DATA-CURATION-GUIDE.md](./TRAIN-DATA-CURATION-GUIDE.md) | Picking pro training videos (torso-normalized separation) |
| [PER-LABEL-TEST-CHECKLIST.md](./PER-LABEL-TEST-CHECKLIST.md) | Smoke + generalization test every new label |
| [OPTIONAL-NEGATIVE-TESTS.md](./OPTIONAL-NEGATIVE-TESTS.md) | Volley gen + negative tests before 5+ labels |
| [SHOT-RETRIEVAL-INVESTIGATION.md](./SHOT-RETRIEVAL-INVESTIGATION.md) | Ongoing investigation playbook |
| [guide/03-mesh-retrieval.md](./guide/03-mesh-retrieval.md) | Architecture |

---

## Key IDs (June 2026 session)

**Analyses**

- Smoke volley: `8622a5b8-b76b-492d-b438-99e679ccb261`
- Smoke return: `f11ae30d-34a7-4665-86a8-a6e876626e3e`
- **Generalization (trust this):** `039a239c-662e-4423-aeab-49dd083a1720`

**Train samples**

- Forehand Return: `4132cf12-613e-4bad-8f81-517b39e6f29c`
- Forehand Volley: `31950f20-dfe8-49c8-a7d7-412604c48a4f`

---

## Reproduce locally

```powershell
cd server
# Requires DATABASE_URL in .env — scripts auto-retry Neon ENOTFOUND
pnpm exec tsx scripts/_e2e_session_investigation.mjs
pnpm exec tsx scripts/_e2e_pose_mesh_compare.mjs
$env:ANALYSIS_ID="039a239c-662e-4423-aeab-49dd083a1720"
$env:BENCH_STEPS="1_library_ready,2_loocv,5_analysis_audit"
pnpm exec tsx scripts/_run_bench_steps.mjs
```

Admin UI: Admin Hub → Training accuracy → Retrieval bench (same steps as HTTP/curl in handover doc).

---

## Suggested senior dev tasks

1. Review scaling risks in handover doc; propose acceptance criteria for `neighbor_distance_gap` as labels grow.
2. Run optional [OPTIONAL-NEGATIVE-TESTS.md](./OPTIONAL-NEGATIVE-TESTS.md) (Volley different-file) before label #3.
3. Apply Neon migration [0030](../server/drizzle/0030_technique_analysis_overview_view.sql) if `_recent_submissions.mjs` is needed.
4. Keep `RETRIEVAL_EMBEDDING_MODE=ensemble` on Railway/server.

---

## Suggested handoff message (copy/paste)

> We validated ensemble shot retrieval end-to-end with a 2-label library. Same-file tests (A/B) prove the pipeline; only analysis `039a239c` is real generalization (different Return video, distance 0.0355, gap 0.179). Start with `docs/SHOT-SYSTEM-VALIDATION-HANDOVER.md` and the `server/scripts/_e2e_*` JSON files. Next bottleneck is training data curation (`docs/TRAIN-DATA-CURATION-GUIDE.md`) and a different-file test per new label — not more smoke tests with the same MP4.
