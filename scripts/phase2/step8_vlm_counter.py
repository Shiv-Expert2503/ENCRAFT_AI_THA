import time
import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from PIL import Image

# --- STRICT PYDANTIC SCHEMAS ---

class CountedSymbol(BaseModel):
    relative_location: str = Field(
        description="Precise spatial location within this tile, e.g., 'Top-left corner near the wall', 'Center, slightly right'."
    )
    confidence: str = Field(
        description="Must be 'High', 'Medium', or 'Low'."
    )
    visual_evidence: str = Field(
        description="Briefly explain what visual features match the target entity."
    )
    needs_human_review: bool = Field(
        description="Set to True if confidence is Medium/Low, or if the symbol is partially obscured/blurry."
    )

class TileAnalysis(BaseModel):
    total_found_in_tile: int = Field(
        description="Total number of valid target entities found in this specific tile."
    )
    symbols: list[CountedSymbol] = Field(
        description="List of individual symbols found in this tile."
    )

# --- CORE FUNCTION ---

def run_vlm_counter(
    tiled_images: list[str], 
    target_entities: list[str], 
    reference_symbol_path: str = None, 
    output_json_path: str = None
) -> dict:
    
    print(f"Starting Phase 2 - VLM Counting for entities: {target_entities}")
    client = genai.Client()
    
    # Load reference image if we extracted one in Phase 1
    ref_img = None
    if reference_symbol_path and Path(reference_symbol_path).exists():
        ref_img = Image.open(reference_symbol_path)
        print("Loaded reference symbol image for grounding.")

    entity_str = ", ".join(target_entities)
    master_results = {
        "target_entities": target_entities,
        "total_found_across_all_tiles": 0,
        "total_flagged_for_review": 0,
        "tiles": {}
    }

    system_instruction = (
        "You are an expert MEP engineering visual inspector. Your job is to count specific symbols on an architectural drawing tile. "
        "You must be precise. Do not guess. If an object is cut off or blurry, log it but mark 'needs_human_review' as true. "
        "Provide spatial locations for every item you find to help the user locate it."
    )

    for tile_path_str in tiled_images:
        tile_path = Path(tile_path_str)
        if not tile_path.exists():
            continue
            
        print(f"Analyzing tile: {tile_path.name}...")
        tile_img = Image.open(tile_path)

        # Construct the dynamic prompt depending on whether we have a reference image
        if ref_img:
            prompt = f"Image 1 is the reference symbol for '{entity_str}'. Image 2 is a tile from the floor plan. How many instances of the reference symbol appear in Image 2?"
            contents = [ref_img, tile_img, prompt]
        else:
            prompt = f"This is a tile from a floor plan. Search carefully and count the instances of: '{entity_str}'."
            contents = [tile_img, prompt]

        # Retry logic for Rate Limits (HTTP 429)
        max_retries = 3
        tile_data = None
        
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=TileAnalysis,
                        temperature=0.0,
                        thinking_config=types.ThinkingConfig(thinking_budget=0)
                    ),
                )
                tile_data: TileAnalysis = response.parsed
                break # Success, exit retry loop
                
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "quota" in error_msg:
                    # wait_time = (2 ** attempt) * 3  # Backoff: 3s, 6s, 12s
                    print(f"Rate limit hit. Retrying in {20} seconds...")
                    time.sleep(20)
                else:
                    print(f"API Error on {tile_path.name}: {e}")
                    break

        # Process the results for this tile
        if tile_data:
            tile_dict = tile_data.model_dump()
            master_results["tiles"][tile_path.name] = tile_dict
            
            master_results["total_found_across_all_tiles"] += tile_dict["total_found_in_tile"]
            
            # Count how many symbols need review in this tile
            flagged_count = sum(1 for sym in tile_dict["symbols"] if sym["needs_human_review"])
            master_results["total_flagged_for_review"] += flagged_count
            
            print(f"  Found: {tile_dict['total_found_in_tile']} | Flagged: {flagged_count}")
        else:
            print(f"  Failed to analyze {tile_path.name}")
            master_results["tiles"][tile_path.name] = {"error": "Analysis failed or rate limited"}

        # Polite delay to prevent hitting the free tier RPM limit too quickly
        time.sleep(20)

    # Save final aggregated results
    if output_json_path:
        out_path = Path(output_json_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(master_results, f, indent=4)
        print(f"\nVLM Counting Complete. Results saved to: {out_path}")

    return master_results