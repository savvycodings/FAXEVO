# Optional tests before scaling past ~5 labels

Run these **before** adding many similar forehand shots (Drive, Topspin, Return, etc.). Not required for the current 2-label library — documented as gaps from the June 2026 validation session.

**Parent:** [SHOT-SYSTEM-VALIDATION-HANDOVER.md](./SHOT-SYSTEM-VALIDATION-HANDOVER.md)

---

## Gap today

| Test | Status (June 2026) |
|------|-------------------|
| Return different-file generalization | **Done** — `039a239c`, distance 0.0355 |
| Volley different-file generalization | **Not done** — only same-file smoke (`8622a5b8`, distance 0) |
| Intentional wrong-shot (negative) | **Not done** — e.g. upload volley, confirm not classified as Return |

---

## Test A — Volley generalization (different file)

**Goal:** Mirror submission C but for Forehand Volley.

1. Train Forehand Volley (already in library — `31950f20`)
2. Analyze a **different** volley video (new person or angle) — bytes must ≠ train volley (3,227,265)
3. Record analysis ID

**Pass criteria:**

| Metric | Target |
|--------|--------|
| Display shot | Forehand Volley |
| Top neighbor | Volley train sample |
| Top distance | **> 0** |
| Gap vs #2 neighbor | Clear margin (track absolute value as library grows) |
| `channel_agreement` | `true` |

```powershell
cd server
$env:ANALYSIS_ID="<volley-generalization-analysis-uuid>"
$env:BENCH_STEPS="5_analysis_audit"
pnpm exec tsx scripts/_run_bench_steps.mjs
```

---

## Test B — Negative / wrong-shot sanity

**Goal:** Confirm the system is not always picking Return when two forehand-family labels exist.

1. Upload/analyze a clip that is **clearly** Forehand Volley (different file from Return train)
2. Confirm top neighbor is **Volley**, not Return
3. Check gap — if Return is #2 with small gap, similar-shot risk is high before adding more labels

**Fail signal:** Volley video classified as Return with small gap — pause library expansion and review train clip separation ([TRAIN-DATA-CURATION-GUIDE.md](./TRAIN-DATA-CURATION-GUIDE.md)).

---

## Test C — LOOCV (when ≥2 clips per label)

Only meaningful after **≥2 different training videos per label**:

```powershell
$env:BENCH_STEPS="2_loocv"
pnpm exec tsx scripts/_run_bench_steps.mjs
```

With 1 clip per label, LOOCV **0/2 top-1** is expected — not a regression.

---

## When to run

| Library size | Run |
|--------------|-----|
| 2 labels (now) | Volley generalization (Test A) recommended before adding label #3 |
| 3–5 labels | Test A + B per new similar family |
| 5+ similar forehands | Test B mandatory; track `neighbor_distance_gap` in admin bench |

---

## Record results here (fill when run)

| Test | Analysis ID | Bytes vs train | Top distance | Gap | Pass? | Date |
|------|-------------|----------------|--------------|-----|-------|------|
| Volley generalization | | | | | | |
| Negative volley→not Return | | | | | | |
