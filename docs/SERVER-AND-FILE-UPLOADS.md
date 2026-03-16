# Server & App: Chat, Files, Images, and File Uploads

## Server layout

| Folder / file | Purpose |
|---------------|--------|
| **`server/src/helpers/`** | Shared utilities (e.g. uploading files to OpenAI). |
| **`server/src/chat/`** | Streaming chat (GPT, Claude, Gemini) and OpenAI Assistants (create-assistant, run-status, thread messages, add-message). |
| **`server/src/files/`** | File-upload route (stub); **not mounted** in `index.ts`. |
| **`server/src/images/`** | Image generation/understanding via Gemini (text → image, or image + prompt). |

---

## 1. Helpers (`server/src/helpers/`)

### `saveFileToOpenai.ts`

- **What it does:** Takes a file (e.g. from multer `req.file`), saves it to disk under `server/uploads/`, then uploads it to the **OpenAI Files API** for use with Assistants.
- **Flow:**
  1. Ensure `uploads/` exists.
  2. Write `file.buffer` to `uploads/<originalname>`.
  3. Build `FormData`: `purpose: 'assistants'`, `file` = blob of that file.
  4. `POST https://api.openai.com/v1/files` with `baseHeaders` (from `utils`).
  5. Returns the API response (includes `id` for the file).
- **Used by:** `chat/createAssistant.ts` and `chat/addMessageToThread.ts` when the user attaches a file (for code_interpreter / retrieval).  
- **Not used by:** `files/upload-file.ts` (that route is a stub and not mounted).

---

## 2. Chat (`server/src/chat/`)

### Mounted routes (in `chatRouter` → `/chat`)

- **`POST /chat/claude`** – Streaming chat with Anthropic Claude (body: `prompt`, `model`; no files).
- **`POST /chat/gpt`** – Streaming chat with OpenAI (body: `messages`, `model`; no files).
- **`POST /chat/gemini`** – Streaming chat with Google Gemini (body: `prompt`, `model`; no files).

All three:

- Accept **JSON body only** (no multipart).
- Stream responses using **Server-Sent Events (SSE)** (`text/event-stream`), ending with `data: [DONE]\n\n`.

So **normal chat does not do file uploads**; it’s text-only.

### Assistant routes (implemented but **not mounted**)

These live in `server/src/chat/` but are **not** registered in `chatRouter` or `index.ts`:

- **`createAssistant`** – Creates an OpenAI Assistant (optionally with an uploaded file via `saveFileToOpenai`), creates a thread, sends the first user message, starts a run. Returns `assistantId`, `threadId`, `runId`.
- **`addMessageToThread`** – Adds a user message to an existing thread (optionally with a file via `saveFileToOpenai`), starts a new run. Returns `runId`.
- **`runStatus`** – Polls run status until completed.
- **`getThreadMessages`** – Fetches thread messages.
- **`runResponse`** – (if used) fetches run response.

To support the Assistant UI you need to:

1. Mount these handlers (e.g. under `/chat/create-assistant`, `/chat/run-status`, etc.).
2. Use **multer** for routes that accept a file (create-assistant, add-message) so `req.file` is set and `saveFileToOpenai` can run.

Until then, the **Assistant screen in the app will get 404** for those endpoints.

---

## 3. Files (`server/src/files/`)

- **`fileRouter`** – Defines `POST /upload-file` → `uploadFile`.
- **`upload-file.ts`** – Stub: reads `prompt` and `codeInterpreter` from `req.body` but does nothing with them and does not handle an actual file upload.
- **Status:** This router is **not** mounted in `server/src/index.ts`, so `/files/upload-file` is not available. Assistant file uploads are intended to go through the **chat** routes (create-assistant / add-message) and `saveFileToOpenai`, not through `/files/upload-file`.

---

## 4. Images (`server/src/images/`)

### Route

- **`POST /images/gemini`** – Single route, with **multer in-memory**: `upload.single('file')`.

### Behavior (`gemini.ts`)

- **Body (one of):**
  - **JSON:** `{ prompt, model }` – text-only request.
  - **Multipart:** `prompt`, `model`, and optional **`file`** (image) – image + text.
- **Models:** `nanoBanana` → `gemini-2.5-flash-image`, `nanoBananaPro` → `gemini-3-pro-image-preview`.
- **Flow:**
  1. Build a `parts` array: if `prompt` → `{ text: prompt }`; if `req.file` → `{ inline_data: { mime_type, data: base64(req.file.buffer) } }`.
  2. `POST` to Gemini `generateContent` with `responseModalities: ["TEXT", "IMAGE"]`.
  3. From the response, find the part with `inlineData` / `inline_data` and return `{ image: "data:<mime>;base64,..." }`.
- **No disk write:** The uploaded image is only in memory (`req.file.buffer`); it’s sent to Gemini as base64 and not stored on the server.

---

## 5. Frontend: how uploads and APIs are used

### `app/src/screens/index.ts`

Re-exports: `Chat`, `Images`, `Settings`, `Onboarding`, `SignIn`, `SignUp`.  
(Assistant is **not** in the tab navigator; it’s a separate screen that could be opened from somewhere else.)

---

### `app/src/screens/chat.tsx`

- **Role:** Streaming text chat (Claude, GPT, Gemini).
- **No file upload.**  
  User types a message; the app builds a `messages` array and calls `getEventSource({ body: { messages, model }, type })` in `utils.ts`, which does a **POST** to `${DOMAIN}/chat/gpt` or `/chat/claude` or `/chat/gemini` with **JSON body**.  
  Responses are consumed via **SSE** and appended to the conversation; Markdown is used to render assistant replies.

---

### `app/src/screens/images.tsx`

- **Role:** Generate images with Gemini (and optionally send an image as input).
- **Upload flow:**
  - User can enter a **prompt** and optionally **pick an image** from the device (`expo-image-picker` → `chooseImage()` → `setImage(asset)`).
  - On **Generate**:
    - **If there is an image:**  
      Builds **FormData**: `file` = `{ uri, name, type: mimeType }` (React Native will send the file), plus `prompt` and `model`.  
      **POST** `${DOMAIN}/images/gemini` with `body: formData` and `Content-Type: 'multipart/form-data'`.
    - **If no image:**  
      **POST** same URL with **JSON** body `{ prompt, model }`.
  - Server responds with `{ image: "data:...;base64,..." }`; the app displays it and allows “Save image” (download to device via `expo-file-system`) and “Clear prompts”.

So **file upload in the app is only used on the Images screen**, and only for the optional image input to Gemini. The server never writes that image to disk; it only forwards it to Gemini as base64.

---

### `app/src/screens/assistant.tsx`

- **Role:** OpenAI Assistant–style chat with optional **instructions** and **file attachment** (e.g. for code_interpreter/retrieval).
- **Upload flow:**
  - User can attach a **document** via `expo-document-picker` → `chooseDocument()` → `setFile(asset)`.
  - When starting a thread (**createThread**) or adding a message (**addMessageToThread**):
    - **If there is a file:**  
      Builds **FormData**: `file` = `{ uri, name, type: mimeType }`, plus `input`, and optionally `instructions` (create) or `thread_id` / `assistant_id` (add message).  
      **POST** to `${DOMAIN}/chat/create-assistant` or `${DOMAIN}/chat/add-message-to-thread` with `body: formData` and `Content-Type: 'multipart/form-data'`.
    - **If no file:**  
      **POST** same URLs with **JSON** body.
  - The app then polls **run-status** and fetches **get-thread-messages**, and renders the thread.

**Important:** These endpoints (`/chat/create-assistant`, `/chat/add-message-to-thread`, etc.) are **not mounted** on the server, so those requests **404**. The server-side handlers exist and are written to use `req.file` and `saveFileToOpenai`; they just need to be registered (and protected with multer for the multipart routes).

---

## 6. Summary table

| Feature        | Server route / handler     | File upload?        | Frontend screen | Notes |
|----------------|----------------------------|----------------------|------------------|--------|
| Text chat      | `/chat/gpt`, `/claude`, `/gemini` | No                   | `chat.tsx`       | JSON + SSE only. |
| Image gen      | `/images/gemini`           | Optional image input | `images.tsx`     | FormData when image chosen; server uses buffer in memory, no disk. |
| Assistant + file | `/chat/create-assistant`, `/add-message-to-thread` (not mounted) | Yes (FormData)       | `assistant.tsx`  | Would use `saveFileToOpenai`; routes need to be mounted + multer. |
| Generic upload | `/files/upload-file` (not mounted) | Stub only            | —                | Not used; Assistant uses chat routes. |

---

## 7. What happens to uploaded files

- **Images screen (`/images/gemini`):**  
  File stays in memory on the server (`req.file.buffer`), is base64’d and sent to Gemini. **Not written to disk.**

- **Assistant (when mounted):**  
  File is passed to `saveFileToOpenai`: written to `server/uploads/<originalname>`, then uploaded to OpenAI Files API. The returned file `id` is sent to the Assistants API. So the file is stored **on disk** in `uploads/` and in **OpenAI’s storage**, not only in memory.

- **Chat (GPT/Claude/Gemini):**  
  No file upload; only JSON messages.
