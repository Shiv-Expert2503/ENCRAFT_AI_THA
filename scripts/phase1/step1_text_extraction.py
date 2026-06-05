import fitz
import json
from pathlib import Path


def test_extract_pdf_vectors(pdf_path, output_path=None, text_output_path=None):
    pdf_path = Path(pdf_path)
    print(f"--- Processing: {pdf_path} ---")

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        print(f"Error opening PDF: {e}")
        return None

    document_inventory = {"total_pages": len(doc), "pages": {}}

    keywords_to_find = ["FLAG NOTES", "GENERAL NOTES", "LEGEND", "ABBREVIATIONS"]

    complete_text_parts = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        page_text = str(page.get_text("text")).strip()
        if page_text:
            complete_text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")

        # Extract text blocks: (x0, y0, x1, y1, "text", block_no, block_type)
        blocks = page.get_text("blocks")

        page_data = {"all_text_blocks": [], "found_targets": {}}

        for b in blocks:
            # block_type 0 means it is text, not an image
            if b[6] == 0:
                # Coordinates are (x0, y0) top-left, (x1, y1) bottom-right
                x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
                text = b[4].strip()

                # Store every block
                page_data["all_text_blocks"].append(
                    {"bbox": [x0, y0, x1, y1], "text": text}
                )

                # Clean text
                clean_text = " ".join(text.split()).upper()

                # Check if contains targets
                for target in keywords_to_find:
                    if target in clean_text:
                        page_data["found_targets"][target] = {
                            "bbox": [x0, y0, x1, y1],
                            "raw_text": text,
                        }
                        print(f" FOUND '{target}' on Page {page_num + 1}")
                        print(
                            f"   Coordinates: [x0:{x0:.2f}, y0:{y0:.2f}, x1:{x1:.2f}, y1:{y1:.2f}]"
                        )

        document_inventory["pages"][f"page_{page_num + 1}"] = page_data

    complete_text = "\n\n".join(complete_text_parts)

    if output_path is None:
        output_path = pdf_path.with_name(f"{pdf_path.stem}_inventory.json")
    else:
        output_path = Path(output_path)

    if text_output_path is None:
        text_output_path = pdf_path.with_name(f"{pdf_path.stem}_complete_text.txt")
    else:
        text_output_path = Path(text_output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    text_output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(document_inventory, f, indent=4)

    with open(text_output_path, "w", encoding="utf-8") as f:
        f.write(complete_text)

    print(f"Full text inventory saved to: {output_path}")
    print(f"Complete text saved to: {text_output_path}\n")

    return {
        "inventory": document_inventory,
        "inventory_path": str(output_path),
        "text_path": str(text_output_path),
        "complete_text": complete_text,
    }


# if __name__ == "__main__":
#     # Define paths relative to the root directory
#     image_1_path = os.path.join("data", "image_1.pdf") # RXR Welcome Center
#     image_2_path = os.path.join("data", "image_2.pdf") # Muswellbrook Depot
#     print(image_1_path, image_2_path)
#     if os.path.exists(image_1_path):
#         test_extract_pdf_vectors(image_1_path)
#     else:
#         print(f"File not found: {image_1_path}. Make sure you are running from the root directory.")

#     if os.path.exists(image_2_path):
#         test_extract_pdf_vectors(image_2_path)
