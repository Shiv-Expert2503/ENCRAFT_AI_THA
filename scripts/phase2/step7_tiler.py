# import os
# import json
# import fitz  # PyMuPDF
# from pathlib import Path


# def generate_overlapping_tiles(image_path, output_dir, grid_size=(3,3), overlap_ratio=0.1):
#     """
#     Slices each page of a PDF into an N x M grid of overlapping tiles.
#     grid_size: (rows, columns). Use (3, 3) for 9 tiles, (4, 4) for 16 tiles.
#     overlap_ratio: 0.10 means a 10% overlap across the seams.
#     """


#     rows, cols = grid_size

#     for page_num in range(len(doc)):
#         page = doc.load_page(page_num)
        
#         # Get logical page dimensions
#         w = page.rect.width
#         h = page.rect.height
        
#         # Calculate overlap in points based on the WHOLE page
#         ox = w * overlap_ratio
#         oy = h * overlap_ratio
        
#         # ---------------------------------------------------------
#         # THE DYNAMIC GRID MATH
#         # ---------------------------------------------------------
#         tile_rects = {}
#         for row in range(rows):
#             for col in range(cols):
#                 # 1. Calculate the base boundaries of the tile
#                 x0 = col * (w / cols)
#                 y0 = row * (h / rows)
#                 x1 = (col + 1) * (w / cols)
#                 y1 = (row + 1) * (h / rows)
                
#                 # 2. Add overlap to the inner seams (don't extend beyond the page)
#                 if col > 0: 
#                     x0 -= ox
#                 if col < cols - 1: 
#                     x1 += ox
#                 if row > 0: 
#                     y0 -= oy
#                 if row < rows - 1: 
#                     y1 += oy
                
#                 # Create a name like "row0_col2" instead of "top_right"
#                 position = f"row{row}_col{col}"
#                 tile_rects[position] = fitz.Rect(x0, y0, x1, y1)
#         # ---------------------------------------------------------

#         page_tiles = {}
#         print(f"Processing Page {page_num + 1} ({w} x {h} pts) into {rows * cols} tiles...")
        
#         for position, rect in tile_rects.items():
#             # Intersect with page rect to prevent out-of-bounds rendering
#             clip_rect = rect.intersect(page.rect)
            
#             # Render the high-res tile
#             pix = page.get_pixmap(clip=clip_rect, dpi=dpi)
            
#             # Save the tile
#             tile_filename = f"{pdf_path.stem}_page{page_num + 1}_{position}.png"
#             tile_filepath = OUTPUT_DIR / tile_filename
#             pix.save(tile_filepath)
            
#             # Save the coordinate mapping math
#             page_tiles[position] = {
#                 "tile_filename": tile_filename,
#                 "logical_bbox": [clip_rect.x0, clip_rect.y0, clip_rect.x1, clip_rect.y1],
#                 "pixel_dimensions": {"width": pix.width, "height": pix.height},
#                 "page_dimensions": {"width": w, "height": h}
#             }
            
#         metadata["pages"][f"page_{page_num + 1}"] = page_tiles

#     # Save the mapping metadata for the aggregation phase
#     metadata_filename = f"{pdf_path.stem}_tile_map.json"
#     metadata_filepath = OUTPUT_DIR / metadata_filename
    
#     with open(metadata_filepath, "w", encoding="utf-8") as f:
#         json.dump(metadata, f, indent=4)
        
#     print(f"🎉 Tiling complete! Metadata saved to {metadata_filepath}")


import os
import json
from pathlib import Path
from PIL import Image

def generate_overlapping_tiles(image_path, output_dir, grid_size=(3, 3), overlap_ratio=0.1):
    """
    Slices a high-res image into an N x M grid of overlapping tiles.
    grid_size: (rows, columns). Use (3, 3) for 9 tiles, (4, 4) for 16 tiles.
    overlap_ratio: 0.10 means a 10% overlap across the seams.
    """
    image_path = Path(image_path)
    output_dir = Path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Load the high-res cropped drawing from Step 6
    img = Image.open(image_path)
    w, h = img.size

    rows, cols = grid_size
    
    # Calculate overlap in pixels based on the whole image
    ox = int(w * overlap_ratio)
    oy = int(h * overlap_ratio)

    tile_paths = []
    
    # Initialize metadata structure for the aggregation phase
    metadata = {
        "source_image": image_path.name,
        "original_dimensions": {"width": w, "height": h},
        "tiles": {}
    }

    print(f"Processing image {image_path.name} ({w} x {h} px) into {rows * cols} tiles...")

    # ---------------------------------------------------------
    # THE DYNAMIC GRID MATH
    # ---------------------------------------------------------
    for row in range(rows):
        for col in range(cols):
            # 1. Calculate the base boundaries of the tile
            x0 = int(col * (w / cols))
            y0 = int(row * (h / rows))
            x1 = int((col + 1) * (w / cols))
            y1 = int((row + 1) * (h / rows))
            
            # 2. Add overlap to the inner seams
            if col > 0: 
                x0 -= ox
            if col < cols - 1: 
                x1 += ox
            if row > 0: 
                y0 -= oy
            if row < rows - 1: 
                y1 += oy
            
            # 3. Clamp to image boundaries to prevent out-of-bounds rendering
            x0 = max(0, x0)
            y0 = max(0, y0)
            x1 = min(w, x1)
            y1 = min(h, y1)
            
            position = f"row{row}_col{col}"
            
            # 4. Crop the tile
            tile = img.crop((x0, y0, x1, y1))
            
            # 5. Save the tile
            tile_filename = f"{image_path.stem}_tile_{position}.png"
            tile_filepath = output_dir / tile_filename
            tile.save(tile_filepath)
            
            tile_paths.append(str(tile_filepath))
            
            # 6. Save the coordinate mapping math
            metadata["tiles"][position] = {
                "tile_filename": tile_filename,
                "pixel_bbox": [x0, y0, x1, y1],
                "tile_dimensions": {"width": tile.width, "height": tile.height}
            }
    # ---------------------------------------------------------

    # Save the mapping metadata for the aggregation phase
    metadata_filename = f"{image_path.stem}_tile_map.json"
    metadata_filepath = output_dir / metadata_filename
    
    with open(metadata_filepath, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)
        
    print(f"Tiling complete. Metadata saved to {metadata_filepath}")

    # Return the list of generated tile paths so the orchestrator can use them in Step 8
    return tile_paths