# Profile Save + Signup Transition Runbook

This runbook prevents two regressions:

1. Profile edits (`username`, `gender`, `name`) do not appear after pressing **Save Changes**.
2. White flash / long blank pause after **Finish Setup** before entering `Technique`.

## Current Architecture (Source of Truth)

- Profile inline edit UI lives in `app/src/screens/Profile.tsx`.
- Basic profile edit API is `POST /api/auth/profile/basic` in `server/src/profile/profileRouter.ts`.
- Profile setup API is `POST /api/auth/profile/setup` (court/ranking flow).
- Auth transition logic lives in `app/App.tsx` (`AuthGate`).

## Guardrails For Profile Edit Persistence

### 1) Ensure request body parsing is active for `/api/auth/profile/*`

`server/src/profile/profileRouter.ts` should include:

- `router.use(express.json())`
- `router.use(express.urlencoded({ extended: true }))`

Why: `/api/auth/profile` is mounted before global body-parser in `server/src/index.ts`, so route-level parsing is required for JSON requests like `/profile/basic`.

### 2) Keep profile save free of stale UI state calls

`app/src/screens/Profile.tsx` `saveBasicProfile()` should:

- call `/profile/basic`
- reload profile via `load()`
- notify header refresh via `props?.onProfileUpdated?.()`

Do not call removed state toggles (for example, stale `setEditMode` after removing edit toggle UX).

### 3) Manual test for profile save

1. Open Profile.
2. Change username and gender.
3. Tap **Save Changes**.
4. Verify immediately:
   - `@username` line updates
   - `Gender: ...` chip updates
   - header mini-profile data refreshes after returning

## Guardrails For Signup Finish Loading / White Flash

### 1) Never return `null` during auth/profile-check transitions

In `app/App.tsx` `AuthGate`:

- For `isPending`, render branded loading screen.
- For `session && !profileChecked`, render branded loading screen.

Returning `null` here causes visible blank/white flashes on some devices.

### 2) Add a short post-setup transition screen

On onboarding completion (`onProfileSetupComplete`):

- set `showPostSetupLoading = true`
- set `profileComplete = true`
- set `profileChecked = true`

Then keep a short minimum loading duration (currently ~2200ms) before rendering main app.

### 3) Keep loading screen style consistent with app

Use:

- same background color (`theme.backgroundColor`)
- existing `Header`
- centered spinner + AI-style status text

This maintains visual continuity and removes abrupt blank frames.

## If White Screen Returns

Quick checks:

1. Confirm `AuthGate` still renders a component (not `null`) for pending/checking states.
2. Confirm `onProfileSetupComplete` still flips `profileComplete/profileChecked`.
3. Confirm no runtime error in `Profile` save path (especially stale state references).
4. Confirm `/api/auth/profile/basic` receives parsed JSON body.

## Recommended Smoke Test Sequence

1. Sign up new user.
2. Complete court/rank setup.
3. Ensure transition screen appears (not white blank).
4. Land on `Technique`.
5. Open Profile.
6. Update username + gender.
7. Save.
8. Verify UI and header reflect new values immediately.
