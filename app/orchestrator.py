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
    from scripts.phase1.step1_text_extraction import test_extract_pdf_vectors
    from scripts.phase1.step2_routing import route_user_query
    from scripts.phase1.step3_legend_extraction import legend_extractor
    from scripts.phase1.step4_symbol_extraction import run_symbol_extraction

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

    step1_result = test_extract_pdf_vectors(
        pdf_path,
        output_path=run_directory / "inventory.json",
        text_output_path=run_directory / "complete_text.txt",
    )
    if step1_result is None:
        raise RuntimeError(f"Text extraction failed for {pdf_path}")

    routing_result = route_user_query(
        prompt,extracted_text_path=step1_result['text_path'], output_path=run_directory / "routing.json"
    )
    routing_payload = routing_result.model_dump()
    routing_payload["prompt"] = prompt
    save_json(run_directory / "routing.json", routing_payload)

    legend_result = None
    legend_image_path = run_directory / "legend.png"
    legend_json_path = run_directory / "legend.json"

    if routing_result.requires_legend_crop:
        legend_result = legend_extractor(pdf_path, legend_image_path, legend_json_path)

    symbol_result = None
    symbol_image_source = None
    symbol_json_path = run_directory / "symbol.json"
    symbol_image_output = run_directory / "symbol.png"
    target_entities = routing_result.target_entities or []

    if routing_result.requires_image_analysis and target_entities:
        if legend_image_path.exists():
            symbol_image_source = legend_image_path
        else:
            symbol_image_source = render_first_page(
                pdf_path, run_directory / "source_page.png"
            )

        symbol_result = run_symbol_extraction(
            image_path=symbol_image_source,
            output_crop_path=symbol_image_output,
            target_entities=target_entities,
            output_json_path=symbol_json_path,
        )

    manifest = {
        "run_directory": str(run_directory),
        "input": input_payload,
        "step1": {
            "inventory_path": step1_result["inventory_path"],
            "text_path": step1_result["text_path"],
        },
        "step2": routing_payload,
        "step3": None if legend_result is None else legend_result.model_dump(),
        "step4": None if symbol_result is None else symbol_result.model_dump(),
        "artifacts": {
            "inventory_json": str(run_directory / "inventory.json"),
            "complete_text": str(run_directory / "complete_text.txt"),
            "routing_json": str(run_directory / "routing.json"),
            "legend_json": str(legend_json_path) if legend_json_path.exists() else None,
            "legend_png": str(legend_image_path)
            if legend_image_path.exists()
            else None,
            "symbol_json": str(symbol_json_path) if symbol_json_path.exists() else None,
            "symbol_png": str(symbol_image_output)
            if symbol_image_output.exists()
            else None,
        },
    }
    save_json(run_directory / "run_manifest.json", manifest)
    return manifest
