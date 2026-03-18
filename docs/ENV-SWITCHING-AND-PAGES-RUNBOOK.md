# xEVO Runbook: Env Switching + Key Page Changes

This file documents:
- what we changed in app pages/backend flow,
- how to switch between **Railway production** and **local development**,
- and how to use **ngrok only where needed**.

---

## 1) Key Page/Flow Changes

### `app/src/screens/technique.tsx`
- 5-step flow after intro/home:
  - Step 1: Player profile (left/right handed + court side)
  - Step 2: Ranking setup (has ranking yes/no, level or source + rating)
  - Step 3: Upload/record
  - Step 4: Marker + clip selection
  - Step 5: Results
- Upload options:
  - Record (camera)
  - Gallery (media library)
- Step 4 marker UI:
  - Reactive scrubber
  - Clip creation (`Set Clip`)
  - Multiple clip list
  - Analyze button gated until at least 1 clip exists
- Background analysis starts after upload (button shows loading/ready state).

### `app/src/screens/SignIn.tsx` and `app/src/screens/SignUp.tsx`
- Header/safe-area alignment updates.
- Better auth session unwrap fixes (`sessionResult.data ?? sessionResult`).
- Cleaner auth error handling (no false success logging).

### `app/src/components/Header.tsx` and `app/src/main.tsx`
- Header logo can reset Technique flow (home-like behavior).

### `server/src/technique/techniqueRouter.ts`
- Upload/analyze/auth flow hardened.
- Guest fallback toggle via env (`ALLOW_GUEST_TECHNIQUE`).
- Video streaming supports range requests (better playback in app/web).
- Analyze now builds `videoUrl` from public base env (important for Modal).

### `server/src/index.ts`
- Better Auth mounted under `/api/auth/*`.
- Technique also aliased under `/api/auth/technique` for current client pathing.
- Auth-route CORS handling for localhost web auth.

---

## 2) Environment Profiles

## A) Railway Production Profile

Use when app/server run against deployed Railway.

### `app/.env`
```env
EXPO_PUBLIC_ENV="PRODUCTION"
EXPO_PUBLIC_DEV_API_URL="https://bexevo-production.up.railway.app"
EXPO_PUBLIC_PROD_API_URL="https://bexevo-production.up.railway.app"
EXPO_PUBLIC_BACKEND_URL="https://bexevo-production.up.railway.app/"
EXPO_PUBLIC_BETTER_AUTH_URL="https://bexevo-production.up.railway.app/"
```

### `server/.env` (Railway env vars)
```env
ENVIRONMENT="PRODUCTION"
BETTER_AUTH_URL="https://bexevo-production.up.railway.app"
PUBLIC_VIDEO_BASE_URL="https://bexevo-production.up.railway.app"
DATABASE_URL="<neon-url>"
MODAL_WEBHOOK_URL="<modal-url>"
ALLOW_GUEST_TECHNIQUE="false"   # set true only for emergency MVP fallback
```

---

## B) Localhost Web + Local Server Profile (Recommended for local browser auth)

Use when testing on your computer browser (`http://localhost:8081`) and local server (`http://localhost:3050`).

### `app/.env`
```env
EXPO_PUBLIC_ENV="DEVELOPMENT"
EXPO_PUBLIC_DEV_API_URL="http://localhost:3050"
EXPO_PUBLIC_PROD_API_URL="https://bexevo-production.up.railway.app"
EXPO_PUBLIC_BACKEND_URL="http://localhost:3050/"
EXPO_PUBLIC_BETTER_AUTH_URL="http://localhost:3050/"
```

### `server/.env`
```env
ENVIRONMENT="DEVELOPMENT"
BETTER_AUTH_URL="http://localhost:3050"
DATABASE_URL="<neon-url>"
MODAL_WEBHOOK_URL="<modal-url>"
ALLOW_GUEST_TECHNIQUE="true"  # optional for MVP fallback
```

Important:
- In this profile, local web auth/cookies should work best.
- `PUBLIC_VIDEO_BASE_URL` is optional unless using remote Modal against local uploads.

---

## C) Localhost + ngrok for Modal Video Fetch (Hybrid)

Use when local app/server run on localhost, but Modal must fetch local uploaded videos.

1. Start ngrok:
```bash
ngrok http 3050
```
2. Copy the HTTPS forwarding URL, e.g.:
`https://xxxx.ngrok-free.dev`
3. Set:

### `server/.env`
```env
BETTER_AUTH_URL="http://localhost:3050"
PUBLIC_VIDEO_BASE_URL="https://xxxx.ngrok-free.dev"
```

This keeps local browser auth on localhost while giving Modal a public URL for `/technique/video/:id`.

---

## 3) Fast Switch Checklist

When switching profiles:
1. Update `app/.env` and `server/.env`.
2. Fully restart local server (`pnpm run dev` in `server`).
3. Restart Expo web/dev server (`app`).
4. If using ngrok, ensure the URL is current (it changes often).
5. Verify logs show expected base URL:
   - `[BetterAuth] Initializing auth { baseURL: ... }`
   - `[Technique] Calling Modal webhook... { videoUrl: ... }`

6. Sanity-check app flow after restart:
   - Intro/home -> profile step -> ranking step -> upload step -> marker step -> results
   - Step indicator shows 5 segments (not 3)

---

## 4) Production Go-Live Sanity Checklist

Before submitting/building for production:
1. `app/.env` points to Railway URLs only (no `localhost`, no ngrok).
2. Railway env has:
   - `ENVIRONMENT="PRODUCTION"`
   - `BETTER_AUTH_URL="https://bexevo-production.up.railway.app"`
   - `PUBLIC_VIDEO_BASE_URL="https://bexevo-production.up.railway.app"` (or your public API domain)
   - `ALLOW_GUEST_TECHNIQUE="false"`
3. Server restart/redeploy completed after env changes.
4. Auth sanity:
   - Sign up works
   - Sign in works
   - Sign out works
5. Technique sanity:
   - Upload succeeds
   - Analyze endpoint returns 200/accepted
   - Results render
6. No local/dev URLs in logs or responses (`localhost`, `ngrok-free.dev`).

---

## 5) Common Failure Patterns

### `No session after sign-in/sign-up`
- Usually env mismatch between app base URL and server `BETTER_AUTH_URL`.
- Restart processes after env edits.

### CORS error: wildcard origin with credentials
- Avoid ngrok browser edge for local auth.
- Prefer localhost web profile for auth testing.

### Analyze 500 with Modal `localhost` connection refused
- `videoUrl` is local and unreachable from Modal.
- Set `PUBLIC_VIDEO_BASE_URL` to ngrok/Railway URL.

### `USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL`
- Not infra failure; use sign-in or different email.

---

## 6) Optional: Keep Two Local Env Files

To make flips easy, keep templates like:
- `app/.env.localhost`
- `app/.env.railway`
- `server/.env.localhost`
- `server/.env.railway`

Then copy the right file over `.env` before starting servers.

