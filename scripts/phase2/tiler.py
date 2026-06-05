# import os
# import json
# import fitz  # PyMuPDF
# from pathlib import Path

# # ==========================================
# # 1. SETUP PATHS
# # ==========================================
# BASE_DIR = Path(__file__).resolve().parent.parent.parent
# DATA_DIR = BASE_DIR / 'data'
# OUTPUT_DIR = BASE_DIR / 'testing' / 'tiles'

# # Make sure output directory exists
# os.makedirs(OUTPUT_DIR, exist_ok=True)

# # ==========================================
# # 2. THE TILING ENGINE
# # ==========================================
# def generate_overlapping_tiles(pdf_path, dpi=400, overlap_ratio=0.10):
#     """
#     Slices each page of a PDF into 4 overlapping quadrants.
#     overlap_ratio: 0.10 means a 10% overlap across the center seams.
#     """
#     print(f"\n--- Tiling PDF: {pdf_path.name} ---")
#     doc = fitz.open(pdf_path)
    
#     metadata = {
#         "file_name": pdf_path.name,
#         "total_pages": len(doc),
#         "pages": {}
#     }

#     for page_num in range(len(doc)):
#         page = doc.load_page(page_num)
        
#         # Get logical page dimensions
#         w = page.rect.width
#         h = page.rect.height
        
#         # Calculate overlap in points
#         ox = w * overlap_ratio
#         oy = h * overlap_ratio
        
#         # Define the 4 overlapping bounding boxes
#         tile_rects = {
#             "top_left": fitz.Rect(0, 0, (w/2) + ox, (h/2) + oy),
#             "top_right": fitz.Rect((w/2) - ox, 0, w, (h/2) + oy),
#             "bottom_left": fitz.Rect(0, (h/2) - oy, (w/2) + ox, h),
#             "bottom_right": fitz.Rect((w/2) - ox, (h/2) - oy, w, h)
#         }
        
#         page_tiles = {}
        
#         print(f"Processing Page {page_num + 1} ({w} x {h} pts)...")
        
#         for position, rect in tile_rects.items():
#             # Intersect with page rect to prevent out-of-bounds rendering
#             clip_rect = rect.intersect(page.rect)
            
#             # Render the high-res tile
#             pix = page.get_pixmap(clip=clip_rect, dpi=dpi)
            
#             # Naming convention: filename_page1_top_left.png
#             tile_filename = f"{pdf_path.stem}_page{page_num + 1}_{position}.png"
#             tile_filepath = OUTPUT_DIR / tile_filename
            
#             pix.save(tile_filepath)
            
#             # CRITICAL: Save the coordinate mapping math
#             # You will need this in Phase 3 to convert the VLM's 0-1000 output 
#             # back to the absolute coordinates of the master page.
#             page_tiles[position] = {
#                 "tile_filename": tile_filename,
#                 "logical_bbox": [clip_rect.x0, clip_rect.y0, clip_rect.x1, clip_rect.y1],
#                 "pixel_dimensions": {"width": pix.width, "height": pix.height},
#                 "page_dimensions": {"width": w, "height": h}
#             }
            
#             print(f"  ✅ Saved {position} tile: {pix.width}x{pix.height} pixels")
            
#         metadata["pages"][f"page_{page_num + 1}"] = page_tiles

#     # Save the mapping metadata for the aggregation phase
#     metadata_filename = f"{pdf_path.stem}_tile_map.json"
#     metadata_filepath = OUTPUT_DIR / metadata_filename
    
#     with open(metadata_filepath, "w", encoding="utf-8") as f:
#         json.dump(metadata, f, indent=4)
        
#     print(f"🎉 Tiling complete! Metadata saved to {metadata_filepath}")

# if __name__ == "__main__":
#     # Test on your PDFs
#     pdf_1 = DATA_DIR / 'image_1.pdf'
#     pdf_2 = DATA_DIR / 'image_2.pdf'
    
#     if pdf_1.exists():
#         generate_overlapping_tiles(pdf_1)
    
#     if pdf_2.exists():
#         generate_overlapping_tiles(pdf_2)


import os
import json
import fitz  # PyMuPDF
from pathlib import Path

# ==========================================
# 1. SETUP PATHS
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / 'data'
OUTPUT_DIR = BASE_DIR / 'testing' / 'tiles'

# Make sure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# 2. THE TILING ENGINE
# ==========================================
def generate_overlapping_tiles(pdf_path, dpi=400, overlap_ratio=0.10, grid_size=(3, 3)):
    """
    Slices each page of a PDF into an N x M grid of overlapping tiles.
    grid_size: (rows, columns). Use (3, 3) for 9 tiles, (4, 4) for 16 tiles.
    overlap_ratio: 0.10 means a 10% overlap across the seams.
    """
    print(f"\n--- Tiling PDF: {pdf_path.name} ({grid_size[0]}x{grid_size[1]} grid) ---")
    doc = fitz.open(pdf_path)
    
    metadata = {
        "file_name": pdf_path.name,
        "total_pages": len(doc),
        "pages": {}
    }

    rows, cols = grid_size

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        
        # Get logical page dimensions
        w = page.rect.width
        h = page.rect.height
        
        # Calculate overlap in points based on the WHOLE page
        ox = w * overlap_ratio
        oy = h * overlap_ratio
        
        # ---------------------------------------------------------
        # THE DYNAMIC GRID MATH
        # ---------------------------------------------------------
        tile_rects = {}
        for row in range(rows):
            for col in range(cols):
                # 1. Calculate the base boundaries of the tile
                x0 = col * (w / cols)
                y0 = row * (h / rows)
                x1 = (col + 1) * (w / cols)
                y1 = (row + 1) * (h / rows)
                
                # 2. Add overlap to the inner seams (don't extend beyond the page)
                if col > 0: 
                    x0 -= ox
                if col < cols - 1: 
                    x1 += ox
                if row > 0: 
                    y0 -= oy
                if row < rows - 1: 
                    y1 += oy
                
                # Create a name like "row0_col2" instead of "top_right"
                position = f"row{row}_col{col}"
                tile_rects[position] = fitz.Rect(x0, y0, x1, y1)
        # ---------------------------------------------------------

        page_tiles = {}
        print(f"Processing Page {page_num + 1} ({w} x {h} pts) into {rows * cols} tiles...")
        
        for position, rect in tile_rects.items():
            # Intersect with page rect to prevent out-of-bounds rendering
            clip_rect = rect.intersect(page.rect)
            
            # Render the high-res tile
            pix = page.get_pixmap(clip=clip_rect, dpi=dpi)
            
            # Save the tile
            tile_filename = f"{pdf_path.stem}_page{page_num + 1}_{position}.png"
            tile_filepath = OUTPUT_DIR / tile_filename
            pix.save(tile_filepath)
            
            # Save the coordinate mapping math
            page_tiles[position] = {
                "tile_filename": tile_filename,
                "logical_bbox": [clip_rect.x0, clip_rect.y0, clip_rect.x1, clip_rect.y1],
                "pixel_dimensions": {"width": pix.width, "height": pix.height},
                "page_dimensions": {"width": w, "height": h}
            }
            
        metadata["pages"][f"page_{page_num + 1}"] = page_tiles

    # Save the mapping metadata for the aggregation phase
    metadata_filename = f"{pdf_path.stem}_tile_map.json"
    metadata_filepath = OUTPUT_DIR / metadata_filename
    
    with open(metadata_filepath, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)
        
    print(f"🎉 Tiling complete! Metadata saved to {metadata_filepath}")

if __name__ == "__main__":
    # Test on your PDFs
    pdf_1 = DATA_DIR / 'image_1.pdf'
    pdf_2 = DATA_DIR / 'image_2.pdf'
    
    if pdf_1.exists():
        generate_overlapping_tiles(pdf_1, dpi=400, grid_size=(3,3))
    
    if pdf_2.exists():
        generate_overlapping_tiles(pdf_2, dpi=400, grid_size=(3,3))