# Pro library training data — curation guide

**Why this matters:** The system matches shots using **torso-normalized body pose** at contact (hip midpoint origin, scale by shoulder–hip distance), plus a **mesh** channel on the same geometry. Training clips must differ **clearly in that space** between labels — not just in filename or stroke name.

**Parent doc:** [SHOT-SYSTEM-VALIDATION-HANDOVER.md](./SHOT-SYSTEM-VALIDATION-HANDOVER.md)

---

## What went wrong before

| Old approach | Problem |
|--------------|---------|
| Re-analyze **same MP4** as training | Distance **0** — proves pipeline, not generalization |
| One clip per label | LOOCV meaningless; no body-type diversity |
| Similar forehand clips (Return vs Drive) without visual separation | Neighbors blur when library grows |

**Current requirement:** Each label needs clips that look **different in embedding space** from every other label at contact, and **≥2 different source videos per label** before trusting accuracy metrics.

---

## Torso-normalized pose — what to look for on video

When picking a training clip, imagine the body **relative to hips/shoulders**, not absolute arm height:

| Good signal at contact | Weak / confusing signal |
|------------------------|-------------------------|
| Clear strike-side arm path (prep → contact → follow) | Idle non-hitting arm position (usually OK if strike side is clear) |
| Distinct stance: volley compact vs groundstroke open | Two shots with same general shape, different names only |
| Full player visible, stable MediaPipe on shoulders/hips/wrists | Occlusion, extreme crop, back to camera at contact |
| YOLO can see racket/ball contact window | Contact off-screen or trim cuts before contact |

**Reference:** Volley train vs Return train in [\_e2e_pose_mesh_compare.json](../server/scripts/_e2e_pose_mesh_compare.json) — volley wrists forward/high (x ~0.7–0.8), return groundstroke lower/compact (x ~0.3–0.5). That separation is what you want **between shot families**.

---

## Clip selection checklist (per label)

Before uploading a pro clip to the library:

- [ ] Label name matches **one** shot type only (no mixed drills in trim)
- [ ] Contact visible inside user trim (or full clip with YOLO contacts)
- [ ] Body geometry at contact looks **visually distinct** from other labels already in library
- [ ] This is clip **#1** or **#2+** for this label (aim for ≥2 **different** source videos per label)
- [ ] Not a duplicate byte-for-byte of an existing train upload (check bytes compare script after upload)

After upload:

- [ ] Run admin bench `1_library_ready`
- [ ] Run **smoke** analyze (same file) → expect top distance ~**0**
- [ ] Run **generalization** analyze (different file, different person if possible) → expect distance **> 0**, correct label, healthy gap

---

## Recommended order as library grows

1. **Distinct families first** — e.g. Forehand Volley vs Forehand Return (proven in June 2026 session)
2. **Add second clip per label** — different pro or angle before adding a 3rd label
3. **Similar forehands** — Return, Drive, Topspin only after each has ≥2 diverse clips and passes different-file tests
4. **Backhand / overhead / lob** — add as separate families when forehand bucket is stable

---

## Minimum library bar before trusting metrics

| Library size | Requirement |
|--------------|-------------|
| 2 labels (current) | 1 generalization test (Return C) — **not enough for production scale** |
| Each new label | Same-file smoke + **different-file** generalization |
| Before LOOCV | **≥2 different videos per label** |
| Before ~5+ similar shots | Optional volley different-file + negative wrong-shot test — see [OPTIONAL-NEGATIVE-TESTS.md](./OPTIONAL-NEGATIVE-TESTS.md) |

---

## After pipeline or Modal changes

Re-extract pro clips — do not rely on embeddings backfill alone:

```http
POST /train/reextract
```

Then re-run `1_library_ready` and spot-check one generalization analysis per label.
