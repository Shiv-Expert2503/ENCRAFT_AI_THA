import json
from pathlib import Path
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from PIL import Image

class SymbolDetectionDetails(BaseModel):
    symbol_found: bool = Field(
        description="True if a Supply Air Swirl Diffuser symbol is explicitly found in the image."
    )
    box_2d: list[int] = Field(
        description="The bounding box of the detected Supply Air Swirl Diffuser in [ymin, xmin, ymax, xmax] standard normalized 0-1000. Return empty list if not found."
    )
    confidence_reasoning: str = Field(
        description="Brief description of where the symbol is located or why it was not found."
    )


# 3. CORE RUNNER PIPELINE
def run_symbol_extraction(
    image_path,
    output_crop_path,
    target_entities=None,
    output_json_path=None,
):
    image_path = Path(image_path)
    output_crop_path = Path(output_crop_path)
    if output_json_path is not None:
        output_json_path = Path(output_json_path)

    client = genai.Client()

    # Open the image using PIL (The SDK can handle local PIL images directly for single images)
    print(f"Loading image asset: {image_path.name}...")
    img = Image.open(image_path)

    entity_text = (
        ", ".join(target_entities) if target_entities else "Supply Air Swirl Diffuser"
    )

    # Refined prompt targeting spatial recognition for engineering icons
    prompt = (
        "Analyze this engineering plan view drawing. Search closely for any of these target entities: "
        f"{entity_text}. "
        "If you locate it, provide its precise localized bounding box layout coordinates "
        "using the [ymin, xmin, ymax, xmax] system standard scaled from 0 to 1000."
    )

    print("Inquiring gemini-2.5-flash for object spatial mapping details...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[img, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SymbolDetectionDetails,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    # Safe object parsing out of response metadata
    data: SymbolDetectionDetails = response.parsed

    payload = data.model_dump()
    payload["input_image_path"] = str(image_path)
    payload["output_crop_path"] = str(output_crop_path)
    payload["target_entities"] = target_entities or []

    if output_json_path is not None:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, indent=4)
        print(f"Symbol response saved to: {output_json_path}")

    if not data.symbol_found or not data.box_2d:
        print(
            f"Analysis Complete: No Supply Air Swirl Diffuser detected. Reason: {data.confidence_reasoning}"
        )
        return data

    print("\n--- Target Symbol Located ---")
    print(f"Coordinates (0-1000 Standard): {data.box_2d}")
    print(f"Reasoning: {data.confidence_reasoning}\n")

    # Execute extraction layout with custom error margin padding
    print("Initiating padding extraction algorithm...")
    crop_image_with_padding(
        img_object=img,
        gemini_box=data.box_2d,
        padding_px=40,  # Adjustable pixel buffer size around all 4 sides
        output_path=output_crop_path,
    )

    return data


# 4. ROBUST PADDING AND CORRECTION CROPPER
def crop_image_with_padding(img_object, gemini_box, padding_px, output_path):
    """
    De-normalizes standard 0-1000 coordinates, appends safe contextual padding,
    clamps calculations within real physical boundaries to prevent errors, and saves crop.
    """
    width, height = img_object.size
    ymin, xmin, ymax, xmax = gemini_box

    # De-normalize coordinates back into true absolute image pixel spaces
    left = int((xmin / 1000) * width)
    top = int((ymin / 1000) * height)
    right = int((xmax / 1000) * width)
    bottom = int((ymax / 1000) * height)

    # Add protective buffer padding uniformly around coordinates
    left_padded = left - padding_px
    top_padded = top - padding_px
    right_padded = right + padding_px
    bottom_padded = bottom + padding_px

    # BOUNDARY CLAMPING: Prevent cropping errors by staying strictly inside image frame walls
    final_left = max(0, left_padded)
    final_top = max(0, top_padded)
    final_right = min(width, right_padded)
    final_bottom = min(height, bottom_padded)

    print(f"Original Box Dimensions: [{left}, {top}, {right}, {bottom}]")
    print(
        f"Padded/Clamped Box Space: [{final_left}, {final_top}, {final_right}, {final_bottom}]"
    )

    # Perform crop segment isolation
    cropped_img = img_object.crop((final_left, final_top, final_right, final_bottom))
    cropped_img.save(output_path)
    print(f"Success! Cropped asset isolated cleanly and saved to: {output_path}")


# if __name__ == "__main__":
#     run_symbol_extraction()
