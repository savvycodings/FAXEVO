import json
import time
import uuid
import requests

BASE = "http://127.0.0.1:8188"
WF_PATH = "/Users/tinhochu/ComfyUI-Installs/ComfyUI/ComfyUI/user/default/workflows/xevo/qwen_image_edit_plus_gguf_correction.api.json"

with open(WF_PATH) as f:
    wf = json.load(f)

wf["41"]["inputs"]["image"] = "xevo_test_main.png"
wf["83"]["inputs"]["image"] = "xevo_test_ref.png"
wf["92"]["inputs"]["image"] = "xevo_test_mask.png"
wf["68"]["inputs"]["prompt"] = (
    "Photorealistic padel court photo. Same player, same court, same lighting, "
    "same clothing and background. Correct the racket-arm position to a proper "
    "ready stance, natural biomechanics, realistic proportions."
)

client_id = str(uuid.uuid4())
resp = requests.post(f"{BASE}/prompt", json={"prompt": wf, "client_id": client_id})
print("queue status:", resp.status_code)
body = resp.json()
print(json.dumps(body, indent=2)[:2000])

if resp.status_code != 200:
    raise SystemExit(1)

prompt_id = body["prompt_id"]
print("prompt_id:", prompt_id)

start = time.time()
last_status = None
while True:
    elapsed = time.time() - start
    if elapsed > 1800:
        print("TIMEOUT after 30 minutes")
        break

    hist = requests.get(f"{BASE}/history/{prompt_id}").json()
    if prompt_id in hist:
        entry = hist[prompt_id]
        status = entry.get("status", {})
        if status.get("completed") is True or status.get("status_str") in ("success", "error"):
            print(f"\nFinished after {elapsed:.0f}s, status: {status}")
            outputs = entry.get("outputs", {})
            print("outputs:", json.dumps(outputs, indent=2))
            break

    # also peek queue for running/pending state + any node errors surfaced there
    q = requests.get(f"{BASE}/queue").json()
    running = q.get("queue_running", [])
    pending = q.get("queue_pending", [])
    cur_status = f"running={len(running)} pending={len(pending)}"
    if cur_status != last_status:
        print(f"[{elapsed:.0f}s] {cur_status}")
        last_status = cur_status

    time.sleep(5)
