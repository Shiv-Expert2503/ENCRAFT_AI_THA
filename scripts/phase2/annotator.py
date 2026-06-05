import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. SETUP PATHS
# ==========================================
# Adjust BASE_DIR depending on where you run the script
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Input Paths
IMAGE_PATH = BASE_DIR / 'testing' / 'tiles' / 'image.png'
JSON_PATH = BASE_DIR / 'data' / 'phase2_output.json'

# Output Path
OUTPUT_DIR = BASE_DIR / 'testing' / 'annotated'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / 'annotated_image.png'

# ==========================================
# 2. THE DRAWING SCRIPT
# ==========================================
def draw_grounded_bboxes():
    print(f"--- Annotating Image: {IMAGE_PATH.name} ---")
    
    # 1. Load the Image
    if not IMAGE_PATH.exists():
        print(f"❌ Error: Image not found at {IMAGE_PATH}")
        return
    img = Image.open(IMAGE_PATH)
    draw = ImageDraw.Draw(img)
    img_width, img_height = img.size
    
    # 2. Load the JSON Data
    if not JSON_PATH.exists():
        print(f"❌ Error: JSON output not found at {JSON_PATH}")
        return
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    findings = data.get("findings", [])
    if not findings:
        print("No findings to draw in the JSON file.")
        return

    print(f"Found {len(findings)} items to draw.")

    # Try to load a default font for text labels, fallback to default if not available
    try:
        font = ImageFont.truetype("arial.ttf", size=24)
    except IOError:
        font = ImageFont.load_default()

    # 3. Loop through findings and draw
    for idx, item in enumerate(findings):
        # Extract the normalized coordinates
        ymin_norm, xmin_norm, ymax_norm, xmax_norm = item["box_2d"]
        
        # Denormalize to actual image pixels
        left = int((xmin_norm / 1000) * img_width)
        top = int((ymin_norm / 1000) * img_height)
        right = int((xmax_norm / 1000) * img_width)
        bottom = int((ymax_norm / 1000) * img_height)
        
        # Determine color based on uncertainty
        requires_review = item.get("requires_human_review", False)
        confidence = item.get("confidence_score", 0)
        
        if requires_review:
            box_color = "red"
            label_text = f"REVIEW: {confidence}%"
        else:
            box_color = "#FF0000"  # Bright Green
            label_text = f"CONF: {confidence}%"

        # Draw the bounding box (line width = 4 pixels for visibility)
        draw.rectangle([left, top, right, bottom], outline=box_color, width=4)
        
        # Optional: Draw a small text label slightly above the box
        # We put a tiny background behind the text so it's readable over the messy blueprint
        text_bbox = draw.textbbox((left, top - 25), label_text, font=font)
        draw.rectangle(text_bbox, fill=box_color)
        draw.text((left, top - 25), label_text, fill="black", font=font)

    # 4. Save the result
    img.save(OUTPUT_PATH)
    print(f"✅ Success! Annotated image saved to: {OUTPUT_PATH}")

if __name__ == "__main__":
    draw_grounded_bboxes()