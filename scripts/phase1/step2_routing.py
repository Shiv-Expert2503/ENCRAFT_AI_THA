# import instructor
# from openai import OpenAI
# import json
# from pathlib import Path
# from pydantic import BaseModel, Field


# class RoutingDecision(BaseModel):
#     requires_image_analysis: bool = Field(
#         description="True if the query requires counting, locating, or visually distinguishing symbols."
#     )
#     requires_legend_crop: bool = Field(
#         description="True if the system needs the legend to know what a specific symbol looks like."
#     )
#     target_pages: list[str] = Field(
#         description="List of specific pages/layouts mentioned, or ['all'] if not specified."
#     )
#     target_entities: list[str] = Field(
#         description="The specific items being searched for, e.g., ['supply air diffuser']."
#     )
#     primary_action: str = Field(
#         description="Must be one of: 'count', 'compare_text', 'find_location', 'extract_notes'."
#     )


# # Instructor patches the client to support response_model
# client = instructor.from_openai(
#     OpenAI(
#         base_url="http://localhost:11434/v1",  # Ollama's local OpenAI-compatible endpoint
#         api_key="llama3.2",  # API key is required by the SDK but ignored by Ollama
#     ),
#     mode=instructor.Mode.JSON,
# )


# def route_user_query(user_query: str, output_path=None) -> RoutingDecision:
#     print(f"Routing query: '{user_query}'...")

#     # 3. CALL THE MODEL WITH GUARANTEED VALIDATION
#     routing_decision = client.chat.completions.create(
#         model="llama3.2",
#         response_model=RoutingDecision,  # This forces the output to match your Pydantic class
#         messages=[
#             {
#                 "role": "system",
#                 "content": "You are an intelligent routing agent for an MEP engineering system. Analyze the user query and populate the required routing fields.",
#             },
#             {"role": "user", "content": user_query},
#         ],
#         max_retries=3,  # If Mistral messes up the JSON, Instructor automatically retries up to 3 times
#     )

#     if output_path is not None:
#         output_path = Path(output_path)
#         output_path.parent.mkdir(parents=True, exist_ok=True)
#         with open(output_path, "w", encoding="utf-8") as file_handle:
#             json.dump(routing_decision.model_dump(), file_handle, indent=4)
#         print(f"Routing decision saved to: {output_path}")

#     return routing_decision


# # if __name__ == "__main__":
# #     q2 = "How many fire dampers are shown on the layouts, and where?"

# #     # The output is no longer a raw dictionary, it is a strongly typed Python object
# #     decision = route_user_query(q2)

# #     print("\n--- Validated Pydantic Object ---")
# #     print(f"Image Analysis: {decision.requires_image_analysis}")
# #     print(f"Entities: {decision.target_entities}")
# #     print(f"Action: {decision.primary_action}")



# switching to gemini since local taking long time
import os
import json
from pathlib import Path
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class RoutingDecision(BaseModel):
    requires_image_analysis: bool = Field(
        description="True if the query requires counting, locating, or visually distinguishing symbols."
    )
    requires_legend_crop: bool = Field(
        description="True if the system needs the legend to know what a specific symbol looks like."
    )
    target_pages: list[str] = Field(
        description="List of absolute 1-indexed PDF page numbers as strings (e.g., ['1', '2']). DO NOT output architectural sheet names like 'ME-1010'. You must map the requested layout to its absolute PDF page number using the provided text. Use ['all'] if no specific page is mentioned."
    )
    target_entities: list[str] = Field(
        description="The specific items being searched for, e.g., ['supply air diffuser']."
    )
    primary_action: str = Field(
        description="Must be one of: 'count', 'compare_text', 'find_location', 'extract_notes'."
    )

# This will automatically pick up the GEMINI_API_KEY from environment variables
client = genai.Client()

def route_user_query(
    user_query: str, 
    extracted_text_path: str | Path = None, 
    output_path: str | Path = None
) -> RoutingDecision:
    
    print(f"Routing query: '{user_query}'...")

    extracted_text = "No extracted text provided."
    if extracted_text_path:
        text_path = Path(extracted_text_path)
        if text_path.exists():
            with open(text_path, "r", encoding="utf-8") as f:
                extracted_text = f.read()
                print(f"Loaded {len(extracted_text)} characters of extracted text context.")
        else:
            print(f"Warning: Extracted text file not found at {text_path}")

    system_instruction = (
        "You are an intelligent routing agent for an MEP engineering system. "
        "Analyze the user query and the provided raw blueprint text to populate the required routing fields."
    )
    
    prompt = f"USER QUERY:\n{user_query}\n\nEXTRACTED BLUEPRINT TEXT:\n{extracted_text}"

    # 3. CALL GEMINI WITH NATIVE STRUCTURED OUTPUTS
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=RoutingDecision,
            temperature=0.0, # Zero temperature ensures deterministic, strict formatting
            thinking_config=types.ThinkingConfig(thinking_budget=0) # Turn off thinking for maximum speed
        ),
    )

    # Gemini automatically parses the JSON into the Pydantic object
    routing_decision: RoutingDecision = response.parsed

    # Save to JSON if requested
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file_handle:
            # .model_dump() safely converts the Pydantic object back to a dictionary
            json.dump(routing_decision.model_dump(), file_handle, indent=4)
        print(f"Routing decision saved to: {output_path}")

    return routing_decision

# if __name__ == "__main__":
#     #api key required seperately here to run from main so ($export)
#     q_test = "What general notes apply to the diffusers and ductwork on this sheet?"
    
#     test_text_path = Path("data/complete_text.txt") 
    
#     decision = route_user_query(
#         user_query=q_test, 
#         extracted_text_path=test_text_path
#     )

#     print("\n--- Validated Pydantic Object ---")
#     print(f"Image Analysis Required: {decision.requires_image_analysis}")
#     print(f"Entities Targeted: {decision.target_entities}")
#     print(f"Action: {decision.primary_action}")