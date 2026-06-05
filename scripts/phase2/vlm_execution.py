import tempfile
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import fitz  # PyMuPDF
from PIL import Image

# 1. SETUP ENVIRONMENT
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
print(ENV_PATH)
load_dotenv(dotenv_path=ENV_PATH)

# ==========================================
# 2. INPUT TOGGLES (Change these as needed)
# ==========================================
PDF_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "image_2.pdf"
# PDF_PATH = Path(__file__).resolve().parent.parent / 'data' / 'image_1.pdf'

# The isolated symbol image we cropped in Phase 1
SYMBOL_REF_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "image.png"

PAGE_NUMBER_0_INDEXED = 2  # e.g., Page 2 is the Upper Ground Floor layout

# The exact question from the prompt
USER_QUERY = "how many of the image symbol appears in the image provided?"
IMAGE_PATH = Path(__file__).resolve().parent.parent.parent / 'testing' / 'tiles' / 'image_2_page3_row0_col.png'


# ==========================================
# 3. DEFINE THE STRUCTURED OUTPUT SCHEMA
# ==========================================
class Finding(BaseModel):
    item_type: str = Field(
        description="The name of the symbol found (e.g., 'Supply Air Diffuser')."
    )
    box_2d: list[int] = Field(
        description="Bounding box [ymin, xmin, ymax, xmax] normalized 0-1000."
    )
    confidence_score: int = Field(
        description="Confidence percentage 0-100. Lower if symbol is obscured by lines."
    )
    requires_human_review: bool = Field(
        description="True if confidence is < 85% or if the symbol is ambiguous/occluded."
    )
    reasoning: str = Field(
        description="Brief explanation of the confidence score (e.g., 'Clear match' or 'Heavily occluded by ductwork')."
    )


class AnswerPayload(BaseModel):
    textual_answer: str = Field(
        description="The direct text answer to the user's question (e.g., explaining the difference between the diffusers)."
    )
    total_count_target_1: int = Field(
        description="Total count of the primary item asked for."
    )
    total_count_target_2: int = Field(
        description="Total count of the secondary item asked for (if applicable, else 0)."
    )
    findings: list[Finding] = Field(
        description="A list of every instance found on the drawing with its coordinates."
    )
    overall_confidence: str = Field(
        description="'HIGH', 'MEDIUM', or 'LOW' based on the clarity of the drawing."
    )


# def export_single_page_pdf(source_pdf_path: Path, PAGE_NUMBER_0_INDEXED: int) -> Path:
#     """Export one page from a multi-page PDF as a temporary single-page PDF.

#     This keeps vector fidelity for MEP drawings while removing unrelated pages.
#     """
#     source_doc = fitz.open(source_pdf_path)
#     page_index = PAGE_NUMBER_0_INDEXED - 1

#     if page_index < 0 or page_index >= len(source_doc):
#         raise ValueError(
#             f"PAGE_NUMBER_0_INDEXED={PAGE_NUMBER_0_INDEXED} is out of range for {source_pdf_path.name}"
#         )

#     single_page_doc = fitz.open()
#     single_page_doc.insert_pdf(source_doc, from_page=page_index, to_page=page_index)

#     temp_file = tempfile.NamedTemporaryFile(
#         suffix=f"_page_{PAGE_NUMBER_0_INDEXED}.pdf",
#         delete=False,
#     )
#     output_path = "data/extracted_single_page.pdf"

#     # 3. Save it directly
#     temp_file.save(output_path)
#     temp_file.close()  # Good practice to free up system memory

#     print(f"PDF page saved successfully to {output_path}")
#     temp_file_path = Path(temp_file.name)
#     temp_file.close()
#     single_page_doc.save(temp_file_path)
#     single_page_doc.close()
#     source_doc.close()

#     return temp_file_path


def export_single_page_pdf(source_pdf_path: Path, PAGE_NUMBER_0_INDEXED: int) -> Path:
    """Export one page from a multi-page PDF as a temporary single-page PDF.

    This keeps vector fidelity for MEP drawings while removing unrelated pages.
    """
    source_doc = fitz.open(source_pdf_path)
    page_index = PAGE_NUMBER_0_INDEXED 

    if page_index < 0 or page_index >= len(source_doc):
        source_doc.close() # Close to prevent memory leak before raising error
        raise ValueError(
            f"PAGE_NUMBER_0_INDEXED={PAGE_NUMBER_0_INDEXED} is out of range for {source_pdf_path.name}"
        )

    # 1. Create a new empty PDF and insert the single page
    single_page_doc = fitz.open()
    single_page_doc.insert_pdf(source_doc, from_page=page_index, to_page=page_index)

    # 2. Setup your target output path safely using Path
    # Going up relative to your script ensures it always lands in the 'data' folder
    root_dir = Path(__file__).resolve().parent.parent.parent
    output_path = root_dir / "data" / "extracted_single_page.pdf"
    
    # Ensure the data directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 3. Tell PyMuPDF to save the data directly to your path string
    single_page_doc.save(str(output_path))
    print(f"PDF page saved successfully to {output_path}")

    # 4. Clean up all opened document instances properly
    single_page_doc.close()
    source_doc.close()

    # 5. Return the Path object pointing to your saved file
    return output_path

# ==========================================
# 4. RUN THE VLM PIPELINE
# ==========================================
def run_vlm_analysis():
    client = genai.Client()

    selected_page_pdf = export_single_page_pdf(PDF_PATH, PAGE_NUMBER_0_INDEXED)


    print(
        f"Uploading page {PAGE_NUMBER_0_INDEXED} from {PDF_PATH.name} and the Reference Symbol to Gemini..."
    )
    # Upload only the requested page as a single-page PDF.
    # uploaded_pdf = client.files.upload(file=selected_page_pdf)
    # # Upload the cropped reference symbol
    uploaded_symbol = client.files.upload(file=SYMBOL_REF_PATH)
    print(f"Loading image asset: {IMAGE_PATH.name}...")
    img = Image.open(IMAGE_PATH)

    # 5. THE ENGINEERED SYSTEM PROMPT
    system_instruction = (
        "You are an expert MEP (Mechanical, Electrical, Plumbing) Construction QA Engineer. "
        "You are analyzing highly complex, dense architectural floor plans. "
        "You have been provided with two files: "
        f"1. The selected blueprint page exported from Page {PAGE_NUMBER_0_INDEXED}. "
        "2. A small reference image containing the exact visual symbols you need to find. "
        "\n\nYOUR TASKS:\n"
        "1. First, answer the text portion of the user's query by analyzing the reference symbols provided. "
        "2. Second, scan the specified page of the blueprint and locate every instance of the requested items. "
        "3. Provide strict [ymin, xmin, ymax, xmax] coordinates normalized from 0-1000 for every finding. "
        "\n\nUNCERTAINTY & GROUNDING RULES (CRITICAL):\n"
        "- MEP drawings contain intersecting lines (ducts, structural grids) that obscure symbols. "
        "- For every finding, assess a 'confidence_score' from 0-100. "
        "- If the symbol is perfectly clear, score it 90-100. "
        "- If a line intersects the symbol making it slightly ambiguous, score it 50-80. "
        "- If the confidence is below 85%, you MUST set 'requires_human_review' to true. Do not guess blindly. It is better to flag an item for review than to hallucinate a construction error. "
        "- If an item is requested but NOT present on the page, state that clearly in the textual answer and return 0 for the count."
    )

    print("\nAnalyzing layout... (This may take 15-30 seconds)")
    response = client.models.generate_content(
        model="gemini-2.5-flash",  # Use Pro here for the heavy lifting/counting across the massive page
        contents=[img, uploaded_symbol, f"User Query: {USER_QUERY}"],
        # contents=[uploaded_pdf, uploaded_symbol, f"User Query: {USER_QUERY}"],
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=AnswerPayload,
            temperature=0.1,  # Low temp for deterministic, analytical counting
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        ),
    )

    if isinstance(response.parsed, AnswerPayload):
        data = response.parsed
    else:
        data = AnswerPayload.model_validate_json(response.text or "{}")

    # 6. OUTPUT AND TRIAGE
    print("\n" + "=" * 50)
    print("VLM ANALYSIS COMPLETE")
    print("=" * 50)
    print(f"Textual Answer: {data.textual_answer}")
    print(f"Count (Target 1): {data.total_count_target_1}")
    print(f"Count (Target 2): {data.total_count_target_2}")
    print(f"Overall Confidence: {data.overall_confidence}")

    print("\n--- Grounded Findings ---")
    flagged_count = 0
    for idx, finding in enumerate(data.findings):
        status = (
            "⚠️ HUMAN REVIEW REQ" if finding.requires_human_review else "✅ CONFIDENT"
        )
        if finding.requires_human_review:
            flagged_count += 1

        print(
            f"{idx + 1}. [{status}] {finding.item_type} @ {finding.box_2d} (Score: {finding.confidence_score}%)"
        )
        print(f"   Reasoning: {finding.reasoning}")

    print("\n--- Summary ---")
    print(f"Total Items Found: {len(data.findings)}")
    print(f"Items Flagged for Review: {flagged_count}")

    # Save the output to JSON for Phase 3 (UI rendering)
    output_path = (
        Path(__file__).resolve().parent.parent.parent / "data" / "phase2_output.json"
    )
    with open(output_path, "w") as f:
        f.write(data.model_dump_json(indent=4))
    print(f"\nRaw JSON saved to {output_path}")

    try:
        selected_page_pdf.unlink(missing_ok=True)
    except OSError:
        pass


if __name__ == "__main__":
    run_vlm_analysis()
