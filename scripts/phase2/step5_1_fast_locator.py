import fitz
from pathlib import Path

def run_fast_text_locator(pdf_path: str, target_entities: list, output_dir: str) -> dict:
    print("\n--- ⚡ Running Fast Path Locator (PyMuPDF) ---")
    doc = fitz.open(pdf_path)
    out_dir = Path(output_dir)
    
    fast_results = {
        "success": False,
        "images": [],
        "entities_found": []
    }

    # Search every page (or you can restrict to target_pages)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        found_on_page = False
        
        for entity in target_entities:
            # We add a quick length check to avoid highlighting the letter 'A' 1000 times
            if len(entity) > 1: 
                rects = page.search_for(entity)
                if rects:
                    found_on_page = True
                    if entity not in fast_results["entities_found"]:
                        fast_results["entities_found"].append(entity)
                    
                    # Draw your thick RED rectangle
                    for rect in rects:
                        # Draw the red box
                        page.draw_rect(rect, color=(1, 0, 0), width=4)
                        # Draw your blue padding box idea
                        padded_rect = rect + fitz.Rect(-50, -50, 50, 50)
                        page.draw_rect(padded_rect, color=(0, 0, 1), width=1, dashes=[5, 5])

        if found_on_page:
            # Render the highlighted page to a high-res PNG
            pix = page.get_pixmap(dpi=200)
            img_path = out_dir / f"fast_locator_page_{page_num + 1}.png"
            pix.save(img_path)
            fast_results["images"].append(str(img_path))
            fast_results["success"] = True

    doc.close()
    return fast_results