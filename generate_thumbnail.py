import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# Canvas Dimensions
CANVAS_W = 1920
CANVAS_H = 1080
PANEL_W = CANVAS_W // 3  # 640

# Fonts
FONT_PATH = "C:/Windows/Fonts/impact.ttf"
FONT_SIZE = 96
font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

# Paths
BASE_DIR = r"c:\Jay\novel\Video_DL\output\he-novice-frontline"
CH1_DIR = os.path.join(BASE_DIR, "chapters", "he-novice-frontline-ch1")

IMG_LEFT_PATH = os.path.join(CH1_DIR, "images", "panels", "page_004_p01.png")
IMG_MID_PATH = os.path.join(CH1_DIR, "images", "panels", "page_010_p02.png")
IMG_RIGHT_PATH = os.path.join(CH1_DIR, "raw_pages", "page_001.jpg")

OUT_THUMBNAIL = os.path.join(BASE_DIR, "THUMBNAIL.jpg")
OUT_THUMBNAIL_CH1 = os.path.join(CH1_DIR, "THUMBNAIL.jpg")

def crop_and_fit(img, target_w, target_h, crop_anchor="center"):
    """Crops and scales image to fill target dimensions without distortion."""
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h
    
    if img_ratio > target_ratio:
        # Image is wider: fit height and crop width
        new_h = target_h
        new_w = round(img.width * target_h / img.height)
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        if crop_anchor == "left":
            left = 0
        elif crop_anchor == "right":
            left = new_w - target_w
        else:
            left = (new_w - target_w) // 2
        return resized.crop((left, 0, left + target_w, target_h))
    else:
        # Image is taller: fit width and crop height
        new_w = target_w
        new_h = round(img.height * target_w / img.width)
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        if crop_anchor == "top":
            top = 0
        elif crop_anchor == "bottom":
            top = new_h - target_h
        else:
            # bias slightly toward top for character portraits
            top = max(0, int((new_h - target_h) * 0.25))
        return resized.crop((0, top, target_w, top + target_h))

# 1. Prepare Base Canvas
canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), "#05070a")

# 2. Process Left Panel (Dying Master)
im_left = Image.open(IMG_LEFT_PATH).convert("RGB")
# Enhance contrast & sharpness slightly for YouTube pop
im_left = ImageEnhance.Contrast(im_left).enhance(1.15)
im_left = ImageEnhance.Color(im_left).enhance(1.1)
panel_left = crop_and_fit(im_left, PANEL_W, CANVAS_H, crop_anchor="top")

# 3. Process Middle Panel (Kid Eo Ja-seo)
im_mid = Image.open(IMG_MID_PATH).convert("RGB")
im_mid = ImageEnhance.Contrast(im_mid).enhance(1.15)
im_mid = ImageEnhance.Color(im_mid).enhance(1.15)
panel_mid = crop_and_fit(im_mid, PANEL_W, CANVAS_H, crop_anchor="top")

# 4. Process Right Panel (Grown-up MC Cover)
im_right = Image.open(IMG_RIGHT_PATH).convert("RGB")
im_right = ImageEnhance.Contrast(im_right).enhance(1.2)
im_right = ImageEnhance.Sharpness(im_right).enhance(1.2)
# Crop around MC face and fist (avoiding the left korean title text if possible, or framing him intensely)
# The MC's face is in the upper-middle right of page_001.jpg
w, h = im_right.size
crop_box = (int(w * 0.15), int(h * 0.05), w, int(h * 0.85))
cropped_mc = im_right.crop(crop_box)
panel_right = crop_and_fit(cropped_mc, PANEL_W, CANVAS_H, crop_anchor="center")

# Paste Panels
canvas.paste(panel_left, (0, 0))
canvas.paste(panel_mid, (PANEL_W, 0))
canvas.paste(panel_right, (PANEL_W * 2, 0))

draw = ImageDraw.Draw(canvas)

# 5. Draw Vertical Dividers (Black thick border with subtle white highlight)
BORDER_THICKNESS = 10
for i in [1, 2]:
    x = i * PANEL_W
    # Outer black glow
    draw.rectangle([x - BORDER_THICKNESS, 0, x + BORDER_THICKNESS, CANVAS_H], fill="#000000")
    # Inner white crisp line
    draw.line([(x, 0), (x, CANVAS_H)], fill="#ffffff", width=3)

# Outer frame borders
draw.rectangle([0, 0, CANVAS_W - 1, CANVAS_H - 1], outline="#000000", width=8)

# 6. Add Bottom Gradient Shadow for Maximum Text Readability
gradient = Image.new("RGBA", (CANVAS_W, 280), (0, 0, 0, 0))
g_draw = ImageDraw.Draw(gradient)
for y in range(280):
    alpha = int(220 * (y / 280) ** 1.3)
    g_draw.line([(0, y), (CANVAS_W, y)], fill=(0, 0, 0, alpha))
canvas.paste(gradient, (0, CANVAS_H - 280), gradient)

# 7. Render Impact Text Labels
labels = [
    (PANEL_W * 0.5, "BEFORE"),
    (PANEL_W * 1.5, "REFUSED!"),
    (PANEL_W * 2.5, "OP MONSTER")
]

TEXT_COLOR = "#FFEE00"  # Vibrant YouTube thumbnail yellow
STROKE_COLOR = "#000000"
STROKE_WIDTH = 9

draw = ImageDraw.Draw(canvas)

for center_x, text in labels:
    bbox = font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    x = center_x - (text_w / 2)
    y = CANVAS_H - text_h - 45
    
    # Draw heavy drop shadow
    for offset_x, offset_y in [(5, 5), (6, 6), (7, 7)]:
        draw.text((x + offset_x, y + offset_y), text, font=font, fill="#000000")
        
    # Draw primary text with thick black outline
    draw.text((x, y), text, font=font, fill=TEXT_COLOR,
              stroke_width=STROKE_WIDTH, stroke_fill=STROKE_COLOR)

# Save high-res JPG
canvas.save(OUT_THUMBNAIL, format="JPEG", quality=95)
canvas.save(OUT_THUMBNAIL_CH1, format="JPEG", quality=95)

print(f"✅ Thumbnail successfully generated at:\n  {OUT_THUMBNAIL}")
