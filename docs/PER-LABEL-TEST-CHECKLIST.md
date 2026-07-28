# Per-label test checklist

Repeat this **every time** you add a new shot label or a second training video to an existing label.

**Parent:** [SHOT-SYSTEM-VALIDATION-HANDOVER.md](./SHOT-SYSTEM-VALIDATION-HANDOVER.md) · [TRAIN-DATA-CURATION-GUIDE.md](./TRAIN-DATA-CURATION-GUIDE.md)

---

## Record sheet (copy per label)

| Field | Value |
|-------|-------|
| Label name | |
| Train sample ID(s) | |
| Smoke analysis ID (same file) | |
| Generalization analysis ID (different file) | |
| Date | |

---

## Step 1 — Train upload

1. Upload pro clip via Admin train flow
2. Confirm indexing completes (40 v2 + 40 sam_v1 rows per sample typical)
3. Run library bench:

```powershell
cd server
$env:BENCH_STEPS="1_library_ready"
pnpm exec tsx scripts/_run_bench_steps.mjs
```

**Pass:** no thin labels at your min threshold; embedding counts grow as expected.

---

## Step 2 — Smoke test (same file)

1. Analyze using the **exact same MP4** used for training (or re-upload same bytes)
2. Note analysis ID from app or Neon

**Pass criteria:**

| Metric | Expected |
|--------|----------|
| Display shot | Matches train label |
| Top neighbor distance | **~0** (same file) |
| `embedding_source` | `ensemble` |
| Verdict | Pipeline OK — **not** generalization evidence |

---

## Step 3 — Generalization test (different file)

1. Analyze a **different** video (different person/angle preferred)
2. Confirm bytes ≠ train source ([\_compare_train_technique_bytes.mjs](../server/scripts/_compare_train_technique_bytes.mjs))

**Pass criteria (only this step counts for label quality):**

| Metric | Expected |
|--------|----------|
| Display shot | Correct label |
| Top neighbor distance | **> 0** (not same file) |
| `neighbor_distance_gap` | Prefer **≥ 0.05**; watch as library grows |
| `channel_agreement` | `true` |
| Top neighbor `stroke_label` | Matches expected train label |

Optional forensics:

```powershell
pnpm exec tsx scripts/_e2e_pose_mesh_compare.mjs
# set ANALYSIS_ID to generalization id
```

---

## Step 4 — Bench audit on generalization analysis

```powershell
$env:ANALYSIS_ID="<generalization-analysis-uuid>"
$env:BENCH_STEPS="5_analysis_audit"
pnpm exec tsx scripts/_run_bench_steps.mjs
```

**Pass:** step `5_analysis_audit` score 100%, predicted shot matches label.

---

## Step 5 — Log results

Update session notes or append row to team spreadsheet:

- Label, train IDs, smoke ID + distance, gen ID + distance + gap, bench pass/fail

If generalization fails: do **not** add more labels until fixed — check train clip quality, similar neighbor labels, or impact frame (YOLO).

---

## Quick script bundle (after generalization analyze)

```powershell
cd server
pnpm exec tsx scripts/_compare_train_technique_bytes.mjs
$env:ANALYSIS_ID="<generalization-analysis-uuid>"
pnpm exec tsx scripts/_e2e_pose_mesh_compare.mjs
$env:BENCH_STEPS="1_library_ready,5_analysis_audit"
pnpm exec tsx scripts/_run_bench_steps.mjs
```

Scripts retry Neon on `ENOTFOUND` via [\_neon_retry.mjs](../server/scripts/_neon_retry.mjs).
