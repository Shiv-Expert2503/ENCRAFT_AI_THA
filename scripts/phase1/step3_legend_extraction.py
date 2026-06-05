import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from PIL import Image
import fitz
from typing import cast

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


class LegendExtractionDetails(BaseModel):
    legend_found: bool = Field(
        description="True if an MEP legend/index or mapping table is located."
    )
    page_number: int = Field(
        description="The 1-indexed page number of the PDF where the legend table lives."
    )
    box_2d: list[int] = Field(
        description="The bounding box of ONLY the legend table/block in [ymin, xmin, ymax, xmax] format normalized 0-1000."
    )
    explanation: str = Field(
        description="Brief explanation of where it was spotted on the page."
    )


def legend_extractor(PDF_PATH, OUTPUT_IMAGE_PATH, OUTPUT_JSON_PATH=None):
    PDF_PATH = Path(PDF_PATH)
    OUTPUT_IMAGE_PATH = Path(OUTPUT_IMAGE_PATH)
    if OUTPUT_JSON_PATH is not None:
        OUTPUT_JSON_PATH = Path(OUTPUT_JSON_PATH)

    client = genai.Client()

    print(f"Uploading {PDF_PATH.name} to Gemini File API...")
    uploaded_file = client.files.upload(file=PDF_PATH)

    prompt = (
        "Analyze this MEP drawing document. Locate the primary Legend, Index, or Abbreviations table. "
        "Identify which page it is on, and provide its exact 2D bounding box "
        "Avoid clipping any symbols or descriptions. Make sure the entire complete region of legend is being captured including all the values and symbols. "
        "coordinates using the [ymin, xmin, ymax, xmax] standard normalized from 0 to 1000."
    )

    print("Analyzing document with gemini-2.5-flash for page and bounding boxes...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[uploaded_file, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=LegendExtractionDetails,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    # Step C: Parse the structured data safely
    # The modern SDK provides parsed pydantic objects directly via response.parsed
    data = cast(LegendExtractionDetails, response.parsed)

    payload = data.model_dump()
    payload["output_image_path"] = str(OUTPUT_IMAGE_PATH)
    payload["output_json_path"] = str(OUTPUT_JSON_PATH) if OUTPUT_JSON_PATH else None

    if OUTPUT_JSON_PATH is not None:
        OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, indent=4)
        print(f"Legend response saved to: {OUTPUT_JSON_PATH}")

    if not data.legend_found:
        print("Gemini could not locate a legend table in this document.")
        return data

    print("\n--- Extraction Target Spotted ---")
    print(f"Page Number: {data.page_number}")
    print(f"Coordinates (0-1000): {data.box_2d}")
    print(f"Details: {data.explanation}\n")

    # Step D: Extract and Crop out the page locally
    # bbox = [182, 30, 563, 649]
    # page_number = 1
    # print(f"Rendering page {page_number} to extract the vector drawing region...")
    # crop_pdf_page(PDF_PATH, page_number, bbox, OUTPUT_IMAGE_PATH)
    print(f"Rendering page {data.page_number} to extract the vector drawing region...")
    crop_pdf_page(PDF_PATH, data.page_number, data.box_2d, OUTPUT_IMAGE_PATH)

    return data


def crop_pdf_page(pdf_path, page_num_1_indexed, gemini_box, output_path):
    """
    Renders a specific page from a PDF and crops out a sub-region
    based on Gemini's normalized 0-1000 coordinates.
    """
    doc = fitz.open(pdf_path)

    # Convert 1-indexed to 0-indexed for python tracking
    page = doc.load_page(page_num_1_indexed - 1)

    # Render page to a high-resolution image object (pixmap)
    # Using matrix zoom increases the DPI so your cropped vectors look crystal clear
    zoom = 2 
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, dpi=600)

    
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    width, height = img.size

    # De-normalize coordinates from gemini's 0-1000 grid
    ymin, xmin, ymax, xmax = gemini_box
    PAD = 30

    left = int((xmin / 1000) * width)
    top = int((ymin / 1000) * height)
    right = int((xmax / 1000) * width)
    bottom = int((ymax / 1000) * height)
    left -= PAD
    top -= PAD
    right += PAD
    bottom += PAD

    # Crop the bounding box segment
    cropped_img = img.crop((left, top, right, bottom))

    # Save the output image
    cropped_img.save(output_path)
    print(f"Success! Cropped legend image saved at: {output_path}")


# PDF_PATH = Path(__file__).resolve().parent.parent / 'data' / 'image_2.pdf'
# OUTPUT_IMAGE_PATH = Path(__file__).resolve().parent.parent / 'data' / 'extracted_legend_test_2.png'
# if __name__ == "__main__":
#     legend_extractor(PDF_PATH, OUTPUT_IMAGE_PATH)
