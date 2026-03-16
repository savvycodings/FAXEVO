# Windows: Metro config load error

On Windows, `pnpm run start` (Expo) can fail with:

```text
Error [ERR_UNSUPPORTED_ESM_URL_SCHEME]: Error loading Metro config at: C:\...\metro.config.cjs
Only URLs with a scheme in: file, data, and node are supported. Received protocol 'c:'
```

This happens because Node's ESM loader is given a Windows absolute path (`C:\...`) instead of a `file://` URL.

## Fix applied in this repo

1. **Config file**  
   The Metro config is **`app/metro.config.cjs`** (CommonJS). No `metro.config.js` is used.

2. **Metro loader patch**  
   The file  
   `app/node_modules/.pnpm/metro-config@0.83.3/node_modules/metro-config/src/loadConfig.js`  
   is patched so that on Windows the path passed to `import()` is converted to a `file://` URL (add `var _url = require("url");` and use `_url.pathToFileURL(absolutePath).href` in the catch block before `import()`).

3. **If the patch is lost**  
   After a fresh `pnpm install`, re-apply the same change to that `loadConfig.js`, or use `pnpm patch metro-config@0.83.3` and `pnpm patch-commit` to make the patch persistent.

## Dependencies

If you see "Cannot find module 'nativewind/metro'", ensure `nativewind`, `class-variance-authority`, and `clsx` are in `app/package.json` dependencies and run `pnpm install` in `app`.
