import fitz  
import cv2
import numpy as np
import os

def extract_and_crop_drawings(pdf_path, page_num_1_indexed, output_dir, dpi=300):
    """
    Extracts a SPECIFIC high-res page, forcefully removes the title block, 
    and uses morphological dilation to isolate stacked drawings.
    Returns a list of the saved image file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    # Convert human page number (1, 2, 3) to computer index (0, 1, 2)
    page_index = page_num_1_indexed - 1
    
    # Boundary check
    if page_index < 0 or page_index >= len(doc):
        print(f"Error: Page {page_num_1_indexed} is out of bounds for document.")
        return []

    page = doc.load_page(page_index)
    zoom = dpi / 72.0 
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    
    img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR) if pix.n == 3 else img_data
        
    # ---------------------------------------------------------
    # 1. THE GUILLOTINE: Remove the right-side title block
    # ---------------------------------------------------------
    crop_w = int(pix.w * 0.84) 
    main_area = img_bgr[:, :crop_w]
    
    # 2. Grayscale & Threshold
    gray = cv2.cvtColor(main_area, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    
    # ---------------------------------------------------------
    # 3. MORPHOLOGICAL DILATION
    # ---------------------------------------------------------
    k_size = int(pix.w * 0.02) 
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))
    dilated = cv2.dilate(thresh, kernel, iterations=1)
    
    # 4. Find Contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    min_area = (crop_w * pix.h) * 0.05
    valid_contours = [c for c in contours if cv2.contourArea(c) > min_area]
    valid_contours = sorted(valid_contours, key=lambda c: cv2.boundingRect(c)[1])
    
    saved_paths = []

    if not valid_contours:
        print(f"No clear drawings found on {base_name} Page {page_num_1_indexed}. Saving fallback.")
        out_path = os.path.join(output_dir, f"{base_name}_page{page_num_1_indexed}_fallback.png")
        cv2.imwrite(out_path, main_area)
        saved_paths.append(out_path)
        return saved_paths

    # 5. Crop using blob boundaries
    for i, contour in enumerate(valid_contours):
        x, y, w, h = cv2.boundingRect(contour)
        
        pad = int(pix.w * 0.01)
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(crop_w, x + w + pad)
        y2 = min(pix.h, y + h + pad)
        
        cropped_drawing = main_area[y1:y2, x1:x2]
        
        out_filename = f"{base_name}_page{page_num_1_indexed}_drawing{i+1}.png"
        out_path = os.path.join(output_dir, out_filename)
        
        cv2.imwrite(out_path, cropped_drawing)
        saved_paths.append(out_path)
        print(f"Saved isolated drawing: {out_path}")

    return saved_paths