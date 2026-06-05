from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
import sys

import fitz

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

OUTPUT_DIR = BASE_DIR / "output"

def _slugify(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in ("-", "_") else "_"
        for character in value
    )
    cleaned = cleaned.strip("_")
    return cleaned or "document"

def create_run_directory(source_name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_directory = OUTPUT_DIR / f"run_{timestamp}_{_slugify(Path(source_name).stem)}"
    run_directory.mkdir(parents=True, exist_ok=False)
    return run_directory

def save_json(output_path: Path, payload: dict[str, Any]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=4, default=str)
    return output_path

def render_first_page(pdf_path: Path, output_path: Path) -> Path:
    doc = fitz.open(str(pdf_path))
    try:
        page = doc.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(str(output_path))
        return output_path
    finally:
        doc.close()

def orchestrate_pdf_run(
    pdf_path: Path, prompt: str, run_directory: Path | None = None
) -> dict[str, Any]:
    
    # --- PHASE 1 IMPORTS ---
    from scripts.phase1.step1_text_extraction import test_extract_pdf_vectors
    from scripts.phase1.step2_routing import route_user_query
    from scripts.phase1.step3_legend_extraction import legend_extractor
    from scripts.phase1.step4_symbol_extraction import run_symbol_extraction
    
    # --- PHASE 2 IMPORTS ---
    from scripts.phase2.step5_text_qa import run_text_qa
    from scripts.phase2.step6_image_extractor import extract_and_crop_drawings

    pdf_path = Path(pdf_path)
    run_directory = (
        Path(run_directory) if run_directory is not None else pdf_path.parent
    )
    run_directory.mkdir(parents=True, exist_ok=True)

    input_payload = {
        "pdf_name": pdf_path.name,
        "pdf_path": str(pdf_path),
        "prompt": prompt,
        "run_directory": str(run_directory),
    }
    save_json(run_directory / "input.json", input_payload)

    # ---------------------------------------------------------
    # PHASE 1 EXECUTION
    # ---------------------------------------------------------
    step1_result = test_extract_pdf_vectors(
        pdf_path,
        output_path=run_directory / "inventory.json",
        text_output_path=run_directory / "complete_text.txt",
    )
    if step1_result is None:
        raise RuntimeError(f"Text extraction failed for {pdf_path}")

    routing_result = route_user_query(
        prompt, extracted_text_path=step1_result['text_path'], output_path=run_directory / "routing.json"
    )
    routing_payload = routing_result.model_dump()
    routing_payload["prompt"] = prompt
    save_json(run_directory / "routing.json", routing_payload)

    # Initialize Manifest structure
    manifest = {
        "run_directory": str(run_directory),
        "input": input_payload,
        "step1": {
            "inventory_path": step1_result["inventory_path"],
            "text_path": step1_result["text_path"],
        },
        "step2": routing_payload,
        "step3": None,
        "step4": None,
        "step5": None,
        "step6": None,
        "artifacts": {
            "inventory_json": str(run_directory / "inventory.json"),
            "complete_text": str(run_directory / "complete_text.txt"),
            "routing_json": str(run_directory / "routing.json"),
        },
    }

    # ---------------------------------------------------------
    # PHASE 2 EXECUTION - BRANCHING
    # ---------------------------------------------------------
    
    # BRANCH A: PURE TEXT PIPELINE
    if not routing_result.requires_image_analysis:
        print("\n---  Routing Path: TEXT ONLY ---")
        text_qa_json_path = run_directory / "text_qa_response.json"
        
        step5_result = run_text_qa(
            user_query=prompt,
            extracted_text_path=step1_result['text_path'],
            output_json_path=text_qa_json_path
        )
        
        manifest["step5"] = step5_result.model_dump()
        manifest["artifacts"]["text_qa_json"] = str(text_qa_json_path)

    # BRANCH B: VISUAL PIPELINE
    else:
        print("\n---  Routing Path: VISUAL ANALYSIS ---")
        
        # Phase 1.5 - Legend Extraction
        legend_image_path = run_directory / "legend.png"
        legend_json_path = run_directory / "legend.json"
        if routing_result.requires_legend_crop:
            legend_result = legend_extractor(pdf_path, legend_image_path, legend_json_path)
            manifest["step3"] = legend_result.model_dump()
            manifest["artifacts"]["legend_json"] = str(legend_json_path) if legend_json_path.exists() else None
            manifest["artifacts"]["legend_png"] = str(legend_image_path) if legend_image_path.exists() else None

        # Phase 1.5 - Symbol Extraction
        symbol_json_path = run_directory / "symbol.json"
        symbol_image_output = run_directory / "symbol.png"
        target_entities = routing_result.target_entities or []
        if target_entities:
            symbol_image_source = legend_image_path if legend_image_path.exists() else render_first_page(pdf_path, run_directory / "source_page.png")
            symbol_result = run_symbol_extraction(
                image_path=symbol_image_source,
                output_crop_path=symbol_image_output,
                target_entities=target_entities,
                output_json_path=symbol_json_path,
            )
            manifest["step4"] = symbol_result.model_dump() if symbol_result else None
            manifest["artifacts"]["symbol_json"] = str(symbol_json_path) if symbol_json_path.exists() else None
            manifest["artifacts"]["symbol_png"] = str(symbol_image_output) if symbol_image_output.exists() else None
        
        # Step 6 - Extract Target Pages
        extracted_pages = []
        if routing_result.target_pages:
            doc_temp = fitz.open(str(pdf_path))
            total_pages = len(doc_temp)
            doc_temp.close()

            pages_to_process = routing_result.target_pages
            if "all" in [p.lower() for p in pages_to_process]:
                pages_to_process = [str(i) for i in range(1, total_pages + 1)]
            
            for p_str in pages_to_process:
                if p_str.isdigit():
                    p_num = int(p_str)
                    if 1 <= p_num <= total_pages:
                        
                        # Call your updated function
                        generated_images = extract_and_crop_drawings(
                            pdf_path=str(pdf_path),
                            page_num_1_indexed=p_num,
                            output_dir=str(run_directory),
                            dpi=300
                        )
                        
                        # Add the newly generated drawing paths to our master list
                        extracted_pages.extend(generated_images)
        
        manifest["step6"] = {"extracted_pages": extracted_pages}
        manifest["artifacts"]["extracted_pages"] = extracted_pages

    save_json(run_directory / "run_manifest.json", manifest)
    return manifest