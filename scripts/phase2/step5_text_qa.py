import json
from pathlib import Path
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class TextQAResponse(BaseModel):
    answer: str = Field(description="The clear, factual answer to the user's question based ONLY on the provided text.")
    confidence: str = Field(description="High, Medium, or Low confidence based on how explicitly the text answers the prompt.")
    found_in_text: bool = Field(description="True if the necessary information was found in the text, False if it is missing.")

def run_text_qa(user_query: str, extracted_text_path: str | Path, output_json_path: str | Path = None) -> TextQAResponse:
    print(f"Running Phase 2 - Text QA for query: '{user_query}'...")

    extracted_text = ""
    text_path = Path(extracted_text_path)
    if text_path.exists():
        with open(text_path, "r", encoding="utf-8") as f:
            extracted_text = f.read()
    else:
        print(f"Warning: Extracted text file not found at {text_path}")

    client = genai.Client()
    system_instruction = (
        "You are an expert MEP engineering assistant. Answer the user's query using ONLY the provided blueprint text. "
        "If the answer cannot be confidently found in the text, set 'found_in_text' to false and state that you cannot find it. "
        "Do not hallucinate or guess."
    )

    prompt = f"USER QUERY:\n{user_query}\n\nBLUEPRINT TEXT:\n{extracted_text}"

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=TextQAResponse,
            temperature=0.0, # Zero temperature for factual consistency
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        ),
    )

    data: TextQAResponse = response.parsed

    if output_json_path:
        output_json_path = Path(output_json_path)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(data.model_dump(), f, indent=4)
        print(f"Text QA response saved to: {output_json_path}")

    return data