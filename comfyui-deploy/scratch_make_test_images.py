from PIL import Image, ImageDraw
import os

COMFY_INPUT = os.path.expanduser("~/ComfyUI-Installs/ComfyUI/ComfyUI/input")
W, H = 768, 1024


def draw_person(draw, cx, cy, scale=1.0, color=(230, 200, 170)):
    # crude humanoid: head, torso, arms, legs - enough pixel structure for a pose
    # detector to have *something* to find, not photorealistic.
    head_r = int(45 * scale)
    draw.ellipse([cx - head_r, cy - head_r, cx + head_r, cy + head_r], fill=color)
    torso_top = cy + head_r
    torso_bot = torso_top + int(220 * scale)
    draw.rectangle([cx - int(55 * scale), torso_top, cx + int(55 * scale), torso_bot], fill=color)
    # arms
    draw.line([cx - int(55 * scale), torso_top + int(20 * scale), cx - int(140 * scale), torso_top + int(140 * scale)], fill=color, width=int(28 * scale))
    draw.line([cx + int(55 * scale), torso_top + int(20 * scale), cx + int(150 * scale), torso_top + int(80 * scale)], fill=color, width=int(28 * scale))
    # legs
    draw.line([cx - int(25 * scale), torso_bot, cx - int(60 * scale), torso_bot + int(260 * scale)], fill=color, width=int(34 * scale))
    draw.line([cx + int(25 * scale), torso_bot, cx + int(55 * scale), torso_bot + int(260 * scale)], fill=color, width=int(34 * scale))


# main frame: green "court" background + person roughly centered
main = Image.new("RGB", (W, H), (40, 110, 60))
d = ImageDraw.Draw(main)
d.rectangle([0, H - 120, W, H], fill=(90, 60, 40))  # ground line
draw_person(d, W // 2, 220, scale=1.0, color=(210, 180, 150))
main.save(os.path.join(COMFY_INPUT, "xevo_test_main.png"))

# ref frame: same scene, slightly different pose offset (stand-in "pro" reference)
ref = Image.new("RGB", (W, H), (40, 110, 60))
d = ImageDraw.Draw(ref)
d.rectangle([0, H - 120, W, H], fill=(90, 60, 40))
draw_person(d, W // 2 + 40, 210, scale=1.05, color=(210, 180, 150))
ref.save(os.path.join(COMFY_INPUT, "xevo_test_ref.png"))

# mask: black bg, white blob over the person's silhouette area (channel=red is read by ImageToMask)
mask = Image.new("RGB", (W, H), (0, 0, 0))
dm = ImageDraw.Draw(mask)
dm.ellipse([W // 2 - 180, 150, W // 2 + 180, 750], fill=(255, 255, 255))
mask.save(os.path.join(COMFY_INPUT, "xevo_test_mask.png"))

print("wrote:", os.listdir(COMFY_INPUT))
