#!/usr/bin/env node
// Posts one machine definition to a self-hosted comfyui-deploy modal-builder /create endpoint.
// Usage:
//   BUILDER_URL=... CALLBACK_URL=... node create-machine.mjs <machine_id> <name> <models-file.json> <GPU> [--force]
//
// GPU must be one of: T4, A10G, A100, L4  (matches builder/modal-builder/src/main.py's GPUType enum)

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const [, , machineId, name, modelsFile, gpu, ...rest] = process.argv;
const force = rest.includes("--force");

if (!machineId || !name || !modelsFile || !gpu) {
  console.error(
    "Usage: node create-machine.mjs <machine_id> <name> <models-file.json> <GPU> [--force]"
  );
  process.exit(1);
}

const VALID_GPUS = ["T4", "A10G", "A100", "L4"];
if (!VALID_GPUS.includes(gpu)) {
  console.error(`GPU must be one of: ${VALID_GPUS.join(", ")}`);
  process.exit(1);
}

const BUILDER_URL = process.env.BUILDER_URL;
const CALLBACK_URL = process.env.CALLBACK_URL;
if (!BUILDER_URL || !CALLBACK_URL) {
  console.error("Set BUILDER_URL and CALLBACK_URL env vars first.");
  process.exit(1);
}

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

// Strip our own doc-only "_"-prefixed keys before building the API payload —
// the real Snapshot/Model schemas (see builder/modal-builder/src/main.py) don't have them.
function stripUnderscoreKeys(obj) {
  if (Array.isArray(obj)) return obj.map(stripUnderscoreKeys);
  if (obj && typeof obj === "object") {
    const out = {};
    for (const [k, v] of Object.entries(obj)) {
      if (k.startsWith("_")) continue;
      out[k] = stripUnderscoreKeys(v);
    }
    return out;
  }
  return obj;
}

const snapshotRaw = readJson(path.join(__dirname, "snapshot.template.json"));
const modelsRaw = readJson(path.join(__dirname, modelsFile));

const snapshot = stripUnderscoreKeys(snapshotRaw);
const models = stripUnderscoreKeys(modelsRaw.models);

// Refuse to deploy placeholder data — this kicks off a real (billed) GPU build.
const payloadText = JSON.stringify({ snapshot, models });
const unresolved = [
  ...new Set(
    (payloadText.match(/REPLACE_WITH[A-Z_]*|"TODO[^"]*"/g) || []).map((s) =>
      s.replace(/^"|"$/g, "")
    )
  ),
];
if (unresolved.length > 0 && !force) {
  console.error(
    `Refusing to deploy: ${unresolved.length} placeholder value(s) still unresolved:\n` +
      unresolved.map((u) => `  - ${u}`).join("\n") +
      "\n\nFill these in (see README.md), or pass --force to deploy anyway."
  );
  process.exit(1);
}

const item = {
  machine_id: machineId,
  name,
  snapshot,
  models,
  callback_url: CALLBACK_URL,
  gpu,
};

console.log(`POST ${BUILDER_URL}/create`);
console.log(`  machine_id: ${machineId}`);
console.log(`  name:       ${name}`);
console.log(`  gpu:        ${gpu}`);
console.log(`  models:     ${models.length}`);

const res = await fetch(`${BUILDER_URL}/create`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(item),
});

const body = await res.text();
if (!res.ok) {
  console.error(`Build request failed (${res.status}): ${body}`);
  process.exit(1);
}
console.log(`Build queued: ${body}`);
console.log(
  `Watch logs at ws(s)://<builder-host>/ws/${machineId} for build progress.`
);
