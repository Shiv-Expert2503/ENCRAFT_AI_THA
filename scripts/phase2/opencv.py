"""
MEP Symbol Counter
==================
Counts occurrences of a target symbol in a specific page of a PDF
using OpenCV multi-scale template matching + NMS.

Inputs:
    - PDF file path
    - Page number (0-indexed)
    - Symbol reference image (PNG/JPG crop from legend)

Output:
    - Count of symbols found
    - Annotated image saved to disk
    - JSON file with all bounding boxes
"""

import json
import sys
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# CONFIGURATION — change these as needed
# ─────────────────────────────────────────────

# Path to your PDF
PDF_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "image_2.pdf"

# Path to the cropped symbol reference image
SYMBOL_REF_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cropped_air_diffuser.png"

# Page number (0-indexed: page 1 = 0, page 2 = 1, etc.)
PAGE_NUMBER_0_INDEXED = 2

# Output folder
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Matching parameters ──────────────────────
# DPI to render the PDF page at (higher = more detail, slower)
RENDER_DPI = 600

# Match threshold: 0.0–1.0. Start at 0.80.
# Raise (0.85–0.90) if you get false positives on similar-looking symbols.
# Lower (0.70–0.75) if you're missing real symbols.
MATCH_THRESHOLD = 0.1

# Scale range to sweep: handles minor DPI mismatches between
# your symbol crop and the rendered PDF page.
SCALE_MIN = 0.40
SCALE_MAX = 2.00
SCALE_STEPS = 20

# NMS overlap threshold: 0.3 is usually good.
# Lower = more aggressive deduplication.
NMS_OVERLAP_THRESH = 0.3

# Binarize images before matching (recommended for MEP/CAD drawings)
# This removes JPEG artifacts and grey anti-aliasing, sharpens match signal.
USE_BINARIZATION = True
BINARIZE_THRESHOLD = 200  # pixels brighter than this → white, else black


# ─────────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────────

def render_pdf_page(pdf_path: Path, page_index: int, dpi: int = 200) -> np.ndarray:
    """
    Render a single PDF page to a numpy BGR image using PyMuPDF.
    """
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    if page_index < 0 or page_index >= total_pages:
        doc.close()
        raise ValueError(
            f"Page index {page_index} out of range. "
            f"PDF has {total_pages} pages (0-indexed: 0 to {total_pages - 1})."
        )

    page = doc[page_index]
    zoom = dpi / 72  # PyMuPDF default is 72 DPI
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    doc.close()

    # Convert to numpy BGR (OpenCV format)
    img_array = np.frombuffer(pix.samples, dtype=np.uint8)
    img = img_array.reshape(pix.height, pix.width, 3)
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img_bgr


def load_symbol(symbol_path: Path) -> np.ndarray:
    """
    Load the symbol reference image. Handles PNG transparency by
    compositing onto white background.
    """
    pil_img = Image.open(str(symbol_path)).convert("RGBA")
    background = Image.new("RGBA", pil_img.size, (255, 255, 255, 255))
    composited = Image.alpha_composite(background, pil_img).convert("RGB")
    img_bgr = cv2.cvtColor(np.array(composited), cv2.COLOR_RGB2BGR)
    return img_bgr


# def preprocess(img_bgr: np.ndarray, binarize: bool = True, thresh: int = 200) -> np.ndarray:
#     """
#     Convert to grayscale and optionally binarize.
#     Binarization is highly recommended for CAD/MEP line drawings.
#     """
#     gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
#     if binarize:
#         _, gray = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
#     return gray

def preprocess(img_bgr: np.ndarray, binarize: bool = True, thresh: int = 200) -> np.ndarray:
    """
    Convert to grayscale and use Edge Detection to isolate shapes,
    making it more robust to intersecting ductwork lines.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    # Standard binarization to clean up anti-aliasing
    if binarize:
        _, gray = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
        
    # Apply Canny Edge Detection
    # This turns solid shapes into thin outlines, drastically improving
    # matchTemplate's ability to handle overlapping CAD lines.
    edges = cv2.Canny(gray, 50, 150)
    
    return edges

def nms(boxes: list, overlap_thresh: float = 0.3) -> list:
    """
    Non-Maximum Suppression.
    Collapses overlapping detections (from multi-scale sweep) into one per symbol.
    boxes: list of [x, y, w, h]
    Returns deduplicated list of [x, y, w, h].
    """
    if not boxes:
        return []

    boxes_arr = np.array(boxes, dtype=float)
    x1 = boxes_arr[:, 0]
    y1 = boxes_arr[:, 1]
    x2 = boxes_arr[:, 0] + boxes_arr[:, 2]
    y2 = boxes_arr[:, 1] + boxes_arr[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = areas.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        inter_w = np.maximum(0.0, xx2 - xx1)
        inter_h = np.maximum(0.0, yy2 - yy1)
        inter = inter_w * inter_h
        iou = inter / (areas[i] + areas[order[1:]] - inter)

        order = order[1:][iou <= overlap_thresh]

    return [boxes_arr[i].astype(int).tolist() for i in keep]


def count_symbols(
    page_img_bgr: np.ndarray,
    symbol_bgr: np.ndarray,
    threshold: float = 0.80,
    scale_min: float = 0.85,
    scale_max: float = 1.15,
    scale_steps: int = 13,
    nms_thresh: float = 0.3,
    binarize: bool = True,
    binarize_thresh: int = 200,
) -> tuple[list, np.ndarray]:
    """
    Core matching function.

    Returns:
        final_boxes: list of [x, y, w, h] for each detected symbol
        annotated:   BGR image with boxes drawn
    """
    gray_page = preprocess(page_img_bgr, binarize, binarize_thresh)
    gray_tmpl = preprocess(symbol_bgr,   binarize, binarize_thresh)

    th, tw = gray_tmpl.shape
    all_boxes = []

    scales = np.linspace(scale_min, scale_max, scale_steps)
    print(f"  Sweeping {len(scales)} scales from {scale_min:.2f}× to {scale_max:.2f}× ...")

    for scale in scales:
        rw = max(4, int(tw * scale))
        rh = max(4, int(th * scale))
        t_resized = cv2.resize(gray_tmpl, (rw, rh), interpolation=cv2.INTER_AREA)

        # Skip if template is larger than the page
        if rh > gray_page.shape[0] or rw > gray_page.shape[1]:
            continue

        result = cv2.matchTemplate(gray_page, t_resized, cv2.TM_CCOEFF_NORMED)
        locs = np.where(result >= threshold)

        for pt in zip(*locs[::-1]):  # locs is (rows, cols) → flip to (x, y)
            all_boxes.append([pt[0], pt[1], rw, rh])

    print(f"  Raw hits before NMS: {len(all_boxes)}")
    final_boxes = nms(all_boxes, nms_thresh)
    print(f"  After NMS: {len(final_boxes)} unique symbols found")

    # Draw results on a copy of the original colour image
    annotated = page_img_bgr.copy()
    for i, (x, y, w, h) in enumerate(final_boxes):
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 200, 80), 2)
        cv2.putText(
            annotated,
            str(i + 1),
            (x, max(y - 5, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 255),
            4,
            cv2.LINE_AA,
        )

    return final_boxes, annotated


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  MEP Symbol Counter")
    print("=" * 55)

    # ── Validate inputs ──────────────────────
    if not PDF_PATH.exists():
        print(f"[ERROR] PDF not found: {PDF_PATH}")
        sys.exit(1)
    if not SYMBOL_REF_PATH.exists():
        print(f"[ERROR] Symbol image not found: {SYMBOL_REF_PATH}")
        sys.exit(1)

    print(f"\n  PDF   : {PDF_PATH.name}")
    print(f"  Symbol: {SYMBOL_REF_PATH.name}")
    print(f"  Page  : {PAGE_NUMBER_0_INDEXED} (0-indexed)")
    print(f"  DPI   : {RENDER_DPI}")
    print(f"  Thresh: {MATCH_THRESHOLD}")

    # ── Step 1: Render PDF page ──────────────
    print("\n[1/4] Rendering PDF page ...")
    page_img = render_pdf_page(PDF_PATH, PAGE_NUMBER_0_INDEXED, dpi=RENDER_DPI)
    print(f"      Page size: {page_img.shape[1]}×{page_img.shape[0]} px")

    # ── Step 2: Load symbol ──────────────────
    print("\n[2/4] Loading symbol reference ...")
    symbol_img = load_symbol(SYMBOL_REF_PATH)
    print(f"      Symbol size: {symbol_img.shape[1]}×{symbol_img.shape[0]} px")

    # ── Step 3: Count ────────────────────────
    print("\n[3/4] Running template matching ...")
    boxes, annotated = count_symbols(
        page_img,
        symbol_img,
        threshold=MATCH_THRESHOLD,
        scale_min=SCALE_MIN,
        scale_max=SCALE_MAX,
        scale_steps=SCALE_STEPS,
        nms_thresh=NMS_OVERLAP_THRESH,
        binarize=USE_BINARIZATION,
        binarize_thresh=BINARIZE_THRESHOLD,
    )

    # ── Step 4: Save outputs ─────────────────
    print("\n[4/4] Saving outputs ...")

    page_label = f"page{PAGE_NUMBER_0_INDEXED + 1}"  # human-friendly (1-indexed)
    stem = PDF_PATH.stem

    annotated_path = OUTPUT_DIR / f"{stem}_{page_label}_annotated.png"
    cv2.imwrite(str(annotated_path), annotated)
    print(f"      Annotated image → {annotated_path}")

    json_path = OUTPUT_DIR / f"{stem}_{page_label}_boxes.json"
    result_data = {
        "pdf": str(PDF_PATH),
        "page_0_indexed": PAGE_NUMBER_0_INDEXED,
        "page_1_indexed": PAGE_NUMBER_0_INDEXED + 1,
        "symbol_ref": str(SYMBOL_REF_PATH),
        "render_dpi": RENDER_DPI,
        "match_threshold": MATCH_THRESHOLD,
        "count": len(boxes),
        "bounding_boxes": [
            {"id": i + 1, "x": x, "y": y, "w": w, "h": h}
            for i, (x, y, w, h) in enumerate(boxes)
        ],
    }
    with open(json_path, "w") as f:
        json.dump(result_data, f, indent=2)
    print(f"      Bounding boxes  → {json_path}")

    # ── Final summary ────────────────────────
    print("\n" + "=" * 55)
    print(f"  ✓ TOTAL SYMBOLS FOUND: {len(boxes)}")
    print("=" * 55)

    return result_data


if __name__ == "__main__":
    load_dotenv()
    main()



# """
# MEP Symbol Counter — Diagnostic Script
# =======================================
# Run this FIRST to figure out why matching returns 0.
# It saves debug images so you can see exactly what both images
# look like after preprocessing, and what the best match score is.
# """

# from pathlib import Path
# import cv2
# import fitz
# import numpy as np
# from PIL import Image

# # ── Same paths as your main script ──────────────────────
# PDF_PATH         = Path(__file__).resolve().parent.parent.parent / "data" / "image_2.pdf"
# SYMBOL_REF_PATH  = Path(__file__).resolve().parent.parent / "data" / "cropped_air_diffuser.png"
# PAGE_INDEX       = 2
# RENDER_DPI       = 400
# DEBUG_DIR        = Path(__file__).resolve().parent / "debug"
# DEBUG_DIR.mkdir(parents=True, exist_ok=True)


# # ─────────────────────────────────────────────────────────
# def render_page(pdf_path, page_index, dpi):
#     doc  = fitz.open(str(pdf_path))
#     page = doc[page_index]
#     zoom = dpi / 72
#     pix  = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
#     doc.close()
#     arr  = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
#     return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

# def load_symbol(path):
#     pil  = Image.open(str(path)).convert("RGBA")
#     bg   = Image.new("RGBA", pil.size, (255, 255, 255, 255))
#     comp = Image.alpha_composite(bg, pil).convert("RGB")
#     return cv2.cvtColor(np.array(comp), cv2.COLOR_RGB2BGR)

# def to_gray(img):        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
# def binarize(gray, t):   _, b = cv2.threshold(gray, t, 255, cv2.THRESH_BINARY); return b
# def otsu(gray):          _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU); return b


# # ─────────────────────────────────────────────────────────
# print("Loading images ...")
# page_bgr   = render_page(PDF_PATH, PAGE_INDEX, RENDER_DPI)
# symbol_bgr = load_symbol(SYMBOL_REF_PATH)

# page_gray   = to_gray(page_bgr)
# symbol_gray = to_gray(symbol_bgr)

# print(f"Page   : {page_bgr.shape[1]}×{page_bgr.shape[0]} px")
# print(f"Symbol : {symbol_bgr.shape[1]}×{symbol_bgr.shape[0]} px")
# print(f"Page   pixel range: min={page_gray.min()}  max={page_gray.max()}  mean={page_gray.mean():.1f}")
# print(f"Symbol pixel range: min={symbol_gray.min()}  max={symbol_gray.max()}  mean={symbol_gray.mean():.1f}")

# # ── Save raw grayscale images ────────────────────────────
# cv2.imwrite(str(DEBUG_DIR / "symbol_gray.png"), symbol_gray)
# print(f"\n→ Saved: debug/symbol_gray.png  ← open this and check it looks correct")

# # Save a 1000×1000 crop from the CENTER of the page (where drawing usually is)
# ch, cw = page_gray.shape
# cx, cy = cw // 2, ch // 2
# crop   = page_gray[cy-500:cy+500, cx-500:cx+500]
# cv2.imwrite(str(DEBUG_DIR / "page_center_crop_gray.png"), crop)
# print(f"→ Saved: debug/page_center_crop_gray.png  ← check if drawing lines are visible here")

# # ── TEST 1: raw grayscale, no binarization ───────────────
# print("\n─── TEST 1: Raw grayscale (no binarization) ───")
# res  = cv2.matchTemplate(page_gray, symbol_gray, cv2.TM_CCOEFF_NORMED)
# _, max_val, _, max_loc = cv2.minMaxLoc(res)
# print(f"  Best match score: {max_val:.4f}  at pixel {max_loc}")

# # ── TEST 2: binarize at 200 ──────────────────────────────
# print("\n─── TEST 2: Binarize threshold=200 ───")
# pb200 = binarize(page_gray, 200)
# sb200 = binarize(symbol_gray, 200)
# cv2.imwrite(str(DEBUG_DIR / "symbol_bin200.png"), sb200)
# cv2.imwrite(str(DEBUG_DIR / "page_center_bin200.png"), binarize(crop, 200))
# res2  = cv2.matchTemplate(pb200, sb200, cv2.TM_CCOEFF_NORMED)
# _, max_val2, _, max_loc2 = cv2.minMaxLoc(res2)
# print(f"  Best match score: {max_val2:.4f}  at pixel {max_loc2}")

# # ── TEST 3: Otsu binarization ────────────────────────────
# print("\n─── TEST 3: Otsu binarization ───")
# pb_otsu = otsu(page_gray)
# sb_otsu = otsu(symbol_gray)
# cv2.imwrite(str(DEBUG_DIR / "symbol_otsu.png"),             sb_otsu)
# cv2.imwrite(str(DEBUG_DIR / "page_center_otsu.png"),        otsu(crop))
# res3  = cv2.matchTemplate(pb_otsu, sb_otsu, cv2.TM_CCOEFF_NORMED)
# _, max_val3, _, max_loc3 = cv2.minMaxLoc(res3)
# print(f"  Best match score: {max_val3:.4f}  at pixel {max_loc3}")

# # ── TEST 4: INVERTED — check if page is dark-on-white but symbol is white-on-dark ──
# print("\n─── TEST 4: Invert symbol, raw gray ───")
# symbol_inv = cv2.bitwise_not(symbol_gray)
# cv2.imwrite(str(DEBUG_DIR / "symbol_inverted.png"), symbol_inv)
# res4  = cv2.matchTemplate(page_gray, symbol_inv, cv2.TM_CCOEFF_NORMED)
# _, max_val4, _, max_loc4 = cv2.minMaxLoc(res4)
# print(f"  Best match score: {max_val4:.4f}  at pixel {max_loc4}")

# # ── TEST 5: multi-scale sweep on best method ─────────────
# print("\n─── TEST 5: Multi-scale sweep (raw gray, scales 0.5–2.0) ───")
# th, tw = symbol_gray.shape
# best_score = 0.0
# best_scale = 1.0
# best_loc   = (0, 0)
# for scale in np.linspace(0.5, 2.0, 31):
#     rw = max(4, int(tw * scale))
#     rh = max(4, int(th * scale))
#     if rh > page_gray.shape[0] or rw > page_gray.shape[1]:
#         continue
#     t = cv2.resize(symbol_gray, (rw, rh), interpolation=cv2.INTER_AREA)
#     r = cv2.matchTemplate(page_gray, t, cv2.TM_CCOEFF_NORMED)
#     _, mv, _, ml = cv2.minMaxLoc(r)
#     if mv > best_score:
#         best_score = mv
#         best_scale = scale
#         best_loc   = ml

# print(f"  Best score across scales: {best_score:.4f}  at scale {best_scale:.2f}×  loc {best_loc}")

# # ── Draw best match location on page (regardless of score) ──
# print("\n─── Saving best-match visualisation ───")
# best_rw  = max(4, int(tw * best_scale))
# best_rh  = max(4, int(th * best_scale))
# vis_page = page_bgr.copy()
# bx, by   = best_loc
# cv2.rectangle(vis_page, (bx, by), (bx + best_rw, by + best_rh), (0, 0, 255), 6)
# cv2.putText(vis_page, f"Best match: {best_score:.3f} @ {best_scale:.2f}x",
#             (bx, max(by - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)

# # Also save a zoomed crop around best match
# pad    = 200
# vis_crop = vis_page[max(0, by-pad):by+best_rh+pad, max(0, bx-pad):bx+best_rw+pad]
# cv2.imwrite(str(DEBUG_DIR / "best_match_region.png"), vis_crop)
# print(f"→ Saved: debug/best_match_region.png  ← does the red box land on a real symbol?")

# # ── SUMMARY ──────────────────────────────────────────────
# print("\n" + "=" * 55)
# print("DIAGNOSIS SUMMARY")
# print("=" * 55)
# scores = {
#     "Raw grayscale":      max_val,
#     "Binarize t=200":     max_val2,
#     "Otsu binarize":      max_val3,
#     "Inverted symbol":    max_val4,
#     "Multi-scale (raw)":  best_score,
# }
# best_method = max(scores, key=scores.get)
# for name, score in scores.items():
#     flag = " ◄ BEST" if name == best_method else ""
#     print(f"  {name:<25} score = {score:.4f}{flag}")

# print()
# if best_score < 0.4:
#     print("⚠  ALL scores very low (<0.4). Likely causes:")
#     print("   • Symbol crop is from a DIFFERENT DPI / zoom level than the page")
#     print("   • Symbol has extra whitespace/padding — crop tighter")
#     print("   • Symbol is colour (e.g. blue lines) but page renders differently")
#     print("   • Wrong page — check page_center_crop_gray.png is the right floor")
# elif best_score < 0.6:
#     print("⚠  Moderate scores (0.4–0.6). Try:")
#     print("   • Use the method with the best score above")
#     print("   • Widen scale range (0.3× – 3.0×) — symbol may be very different size")
#     print("   • Check symbol_gray.png — does it look clean?")
# else:
#     print(f"✓  Good score ({best_score:.3f}) found with '{best_method}'!")
#     print(f"   → Use threshold ~{best_score * 0.85:.2f} in main script")
#     print(f"   → Open debug/best_match_region.png to confirm red box hits a real symbol")

# print("\nDebug images saved to:", DEBUG_DIR)
# print("Open them to visually confirm what each preprocessing step produces.")