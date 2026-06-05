import fitz
from pathlib import Path

def run_fast_text_locator(pdf_path: str, target_entities: list, output_dir: str) -> dict:
    print("\n--- ⚡ Running Fast Path Locator (PyMuPDF Exact Match) ---")
    doc = fitz.open(pdf_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    fast_results = {
        "success": False,
        "images": [],
        "entities_found": []
    }

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        found_on_page = False
        
        # Extract all distinct words on the page
        # w format: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
        words = page.get_text("words")
        
        for entity in target_entities:
            # We can now safely lower the length check to 1 if needed, 
            # because we are doing EXACT whole-word matching!
            if len(entity) >= 1: 
                
                # Loop through every word and check for a strict exact match
                for w in words:
                    # Clean the PDF word of any stray punctuation just in case
                    pdf_word = w[4].strip(".,;:()")
                    
                    if pdf_word == entity:
                        found_on_page = True
                        if entity not in fast_results["entities_found"]:
                            fast_results["entities_found"].append(entity)
                        
                        # Grab exact coordinates of that specific word
                        rect = fitz.Rect(w[0], w[1], w[2], w[3])
                        
                        # Draw the red box
                        page.draw_rect(rect, color=(1, 0, 0), width=3)
                        # Draw your blue padding box
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