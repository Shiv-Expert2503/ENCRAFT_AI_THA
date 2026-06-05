import json
from pathlib import Path
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from PIL import Image

class SelfReflectionReport(BaseModel):
    first_person_summary: str = Field(
        description="A first-person paragraph ('I found...', 'I noticed...') stating the total count, assessing how difficult the visual search was based on the image density/symbol size, and asking the user to verify if the scene was complex."
    )
    needs_human_verification: bool = Field(
        description="True if the symbol is very small, the drawing is dense/complex, or overlapping lines make counting difficult."
    )

def run_validator(user_query: str, len_of_images: int, step8_results: dict, symbol_path: str, sample_image_path: str, output_json_path: str = None) -> dict:
    print("\n--- Executing Phase 2: Step 9 Self-Reflection Auditor ---")
    
    client = genai.Client()
    contents = []

    # Load the symbol and a sample of the floor plan so the LLM can judge "complexity"
    if symbol_path and Path(symbol_path).exists():
        contents.append(Image.open(symbol_path))
        contents.append("Image 1: The reference symbol I was looking for.")
        
    if sample_image_path and Path(sample_image_path).exists():
        contents.append(Image.open(sample_image_path))
        contents.append("Image 2: A sample of the floor plan I was searching.")

    total_counted = step8_results.get('total_found_across_all_tiles', 0)

    # system_instruction = (
    #     "You are an AI assistant that just completed a visual counting task on an MEP engineering drawing. "
    #     "You must now write a self-reflective summary for the user in the FIRST PERSON ('I'). "
    #     "Assess the visual complexity of the floor plan (Image 2) compared to the target symbol (Image 1). "
    #     "If the symbol is tiny, the drawing is cluttered, or ducts are overlapping, you must admit that there is a high "
    #     "chance of error and explicitly ask the user to verify your count."
    # )
    system_instruction = (
        "You are an AI assistant that just completed a visual analysis task on an MEP engineering drawing. "
        "You must now write a self-reflective summary for the user in the FIRST PERSON ('I'). "
        "IMPORTANT: Do NOT refer to 'Image 1' or 'Image 2' in your text. Speak naturally, e.g., 'the symbol' or 'the floor plan'. "
        "1. Read the USER QUERY to understand what was asked (e.g., counting, locating, or identifying). "
        "2. Read the RAW FINDINGS to see what you discovered. "
        "3. Write a summary that directly answers their query based on those findings. "
        "4. Assess the visual complexity of the floor plan compared to the target symbol. If the drawing is cluttered, "
        "admit there is a high chance of error and ask the user to verify your work."
    )

    # prompt = (
    #     f"USER QUERY: '{user_query}'\n"
    #     f"I just finished analyzing the tiles and found a total of {total_counted} items. "
    #     f"Look at the density of the sample floor plan provided. Write a natural, first-person summary stating how many "
    #     f"I found, how difficult/complex the drawing is, and whether the user needs to double-check my work."
    #     f"Here is the total number of images I scanned {len_of_images} and here is one image "
    # )
    # prompt = (
    #     f"USER QUERY: '{user_query}'\n"
    #     f"I just finished analyzing the tiles and found a total of {total_counted} items across {len_of_images} extracted drawing pages. "
    #     f"Look at the density of the random sample floor plan provided. Write a natural, first-person summary stating how many "
    #     f"I found, how difficult/complex the drawing is, and whether the user needs to double-check my work."
    # )
    prompt = (
        f"USER QUERY: '{user_query}'\n"
        f"MY RAW FINDINGS: {json.dumps(step8_results)}\n"
        f"I scanned {len_of_images} extracted drawing pages to find this information.\n\n"
        f"Look at the density of the sample floor plan provided. Write your natural, first-person summary now."
    )
    contents.append(prompt)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=SelfReflectionReport,
            temperature=0.5, # Slight temperature for natural language generation
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        ),
    )

    audit_data = response.parsed.model_dump()
    
    if output_json_path:
        out_path = Path(output_json_path)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(audit_data, f, indent=4)
        print(f"Reflection report saved to: {out_path}")

    return audit_data