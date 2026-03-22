# Pose Correction Quality Upgrades

This document defines the next set of upgrades to improve corrected-pose image quality while keeping the current XEVO pipeline stable.

Focus areas:

- prevent handedness swaps (left/right mirroring mistakes),
- keep racket present and anatomically consistent,
- improve shot-specific biomechanical realism,
- preserve current architecture (`techniqueRouter` + `frameExtractor` + `correctionPrompt`) and incrementally enhance prompting.

---

## Why we are changing this

Current issues observed in generated corrections:

- dominant hand sometimes flips,
- forehand/backhand interpretation can be camera-centric instead of player-centric,
- racket can disappear or be deformed,
- overhead families (bandeja/vibora/smash) can collapse into generic overhead posture.

The main hypothesis is correct: we need better structured prompting and stronger invariants, not a full pipeline rewrite.

---

## What stays the same

- Frame extraction remains in `server/src/technique/frameExtractor.ts`.
- Endpoint orchestration remains in `server/src/technique/techniqueRouter.ts` (`POST /technique/correction-images`).
- Image model remains Gemini image generation in `server/src/technique/correctionPrompt.ts`.
- Corrections are still returned/cached as `{ frame, originalImage, correctedImage }`.

---

## New conceptual layer to add

Add a **movement-intent conditioning layer** before image generation.

Today:

1) recommendations -> landmark deltas (GPT) -> Gemini prompt

Target:

1) shot/movement classification + handedness lock (GPT)
2) recommendations -> landmark deltas (GPT)
3) strict invariants + canonical movement representation -> Gemini prompt

This preserves existing flow but provides richer, more constrained context to the image model.

---

## Benjamin taxonomy integration (what to add)

### 1) Shot classification schema (player-centric)

Add a structured object matching the core ideas from Benjamin’s email:

- shot family/name/variant,
- tactical role and court zone,
- ball context and contact timing,
- spin profile and objective,
- start/middle/final body positions,
- common confusions,
- confidence.

### 2) Mandatory handedness block

Always generate and pass:

- `dominant_hand`: right-handed | left-handed | unknown,
- confidence score,
- evidence list.

Enforce this in every prompt stage.

### 3) Hard invariants for generation

Inject explicit non-negotiables into Gemini prompt:

- do not mirror player anatomy,
- preserve dominant hand side,
- preserve racket existence and attachment to dominant hand,
- keep identity/clothing/court/camera unchanged,
- only modify biomechanical posture elements requested.

---

## Code changes by file

## A) `server/src/technique/correctionPrompt.ts`

Add new types:

- `ShotClassification`
- `HandednessClassification`
- `CanonicalMovementFrame` (start/middle/final descriptors)

Add new function:

- `classifyShotAndHandedness(...)`
  - input: frame landmarks, nearby frame landmarks, diagnosis/recommendations, optional metadata
  - output: structured shot + handedness object

Update `generateCorrectedImage(...)` signature to accept:

- `shotClassification`,
- `handedness`,
- optional `invariants`.

Update Gemini prompt builder:

- include handedness lock section,
- include anti-mirroring rule,
- include racket continuity rule,
- include shot-family-specific movement cues.

## B) `server/src/technique/techniqueRouter.ts`

Inside `/correction-images`:

- compute classification once per frame (or reuse per-shot cluster if optimized),
- pass classification + handedness to `generateCorrectedImage(...)`,
- log classification confidence and handedness evidence.

No endpoint contract change required for the client in phase 1.

## C) `app/src/screens/technique.tsx` (optional phase)

Optional debug-only addition:

- feature flag to display server-provided `dominant_hand` and `shot_name` per frame for QA verification.

This is optional and should not block backend quality work.

---

## Prompt architecture update

Use two prompt tracks:

### Track 1: movement intelligence (GPT)

Goal:

- classify shot from movement + context (not name),
- determine handedness with evidence,
- output canonical schema.

Important rules to embed:

- player-centric laterality (not camera-centric),
- preserve left-handed interpretation when detected,
- distinguish bandeja vs vibora vs smash by intent and kinematics,
- distinguish salida vs bajada by rebound + attack profile.

### Track 2: image correction (Gemini)

Goal:

- regenerate same frame with corrected body mechanics.

Prompt must include:

- canonical movement summary,
- handedness lock block,
- landmark deltas,
- strict invariants list.

---

## Minimum invariants block (recommended exact language)

Use this invariant section in Gemini prompt:

1. Preserve player identity, clothing, court, camera angle, and lighting.
2. Preserve player handedness exactly as provided; do not mirror.
3. Keep the racket visible in the dominant hand; do not remove or relocate it.
4. Maintain forehand/backhand interpretation relative to player orientation, not image left/right.
5. Modify only biomechanical posture requested by corrections.
6. Do not add text, labels, overlays, extra objects, or style changes.

---

## Quality gates and evaluation

Track these failure classes per generated frame:

- `handedness_swap`
- `racket_missing_or_broken`
- `camera_mirror_error`
- `wrong_shot_family_posture`
- `identity_or_scene_drift`

Recommended QA scorecard (0/1 each):

- handedness preserved,
- racket preserved,
- shot-family posture credible,
- original identity/background preserved,
- correction intent visible.

Acceptance target for rollout:

- >= 90% pass on handedness + racket + identity across internal validation set.

---

## Rollout plan

### Phase 1 (safe upgrade, no API contract changes)

- Add classification + handedness generation.
- Add prompt invariants.
- Keep response payload unchanged.

### Phase 2 (observability)

- Persist debug metadata in `metrics.correction_debug`:
  - shot name,
  - handedness,
  - confidence,
  - failure flags.

### Phase 3 (optimization)

- Cache classification results per analysis.
- Reuse across frames where context is stable.

---

## Ownership (who changes what)

- **Backend AI/Prompt engineer**
  - `correctionPrompt.ts`
  - prompt templates
  - classification schema + invariant rules

- **Backend API engineer**
  - `techniqueRouter.ts` integration
  - logging/caching/debug metadata

- **Mobile engineer**
  - optional debug rendering in `technique.tsx`
  - no blocking changes for phase 1

- **Padel domain reviewer / coach**
  - taxonomy validation (bandeja/vibora/smash, salida/bajada, chiquita/lob)
  - ambiguity resolution guidelines

- **QA**
  - failure tagging and acceptance metrics
  - regression checks across right-handed and left-handed clips

---

## Risks and mitigations

- Risk: over-constrained prompt reduces correction strength.
  - Mitigation: keep invariants strict, but allow moderate movement deltas.

- Risk: handedness classification uncertain in some frames.
  - Mitigation: use multi-frame evidence (previous/next frame), return `unknown` when confidence is low.

- Risk: higher latency from extra GPT call.
  - Mitigation: cache classification per analysis and reuse across frames.

---

## Summary

We are not replacing the current working pipeline.

We are strengthening it by adding:

- movement-aware shot taxonomy conditioning,
- explicit handedness detection + lock,
- strict racket and anti-mirroring invariants,
- better QA observability.

This should directly reduce hand-swap and racket-loss artifacts while improving corrected-pose realism.
