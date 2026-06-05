import streamlit as st
from pathlib import Path

# Import your existing orchestrator functions
from orchestrator import create_run_directory, orchestrate_pdf_run
from dotenv import load_dotenv

# 1. LOAD ENV VARS FIRST
load_dotenv()

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Encraft AI - MEP Assistant", page_icon="🏗️", layout="wide"
)

st.title("🏗️ MEP Blueprint AI Assistant")
st.markdown(
    "Upload a mechanical drawing and ask questions. The AI agent will route the query, extract the legend, isolate symbols, and ground its findings."
)

# --- SIDEBAR: FILE UPLOAD ---
with st.sidebar:
    st.header("1. Document Upload")
    uploaded_file = st.file_uploader("Upload MEP PDF (.pdf)", type=["pdf"])
    st.info(
        "The system automatically runs OCR, vector extraction, and semantic routing."
    )

# --- MAIN UI: PROMPT & EXECUTION ---
st.header("2. Ask the Blueprint")
prompt = st.text_area(
    "User Query:",
    placeholder="e.g., How many fire dampers are shown on the layouts, and where?",
    height=100,
)

if st.button("Run AI Pipeline", type="primary"):
    if not uploaded_file:
        st.error("⚠️ Please upload a PDF blueprint first.")
        st.stop()
    if not prompt.strip():
        st.error("⚠️ Please enter a question.")
        st.stop()

    # --- PIPELINE EXECUTION ---
    with st.status("Running AI Agents...", expanded=True) as status:
        try:
            # 1. Setup file paths
            st.write("📁 Creating run directory...")
            run_dir = create_run_directory(uploaded_file.name)
            pdf_path = run_dir / uploaded_file.name

            # 2. Save the uploaded file from Streamlit's memory to disk
            with open(pdf_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            # 3. Trigger the orchestrator
            st.write("🧠 Routing query and extracting vectors...")
            manifest = orchestrate_pdf_run(pdf_path, prompt, run_dir)

            status.update(label="Pipeline Complete!", state="complete", expanded=False)

        except Exception as e:
            status.update(label="Pipeline Failed", state="error")
            st.error(f"An error occurred: {e}")
            st.stop()

    # --- RESULTS DISPLAY ---
    st.success("Analysis Finished Successfully!")

    st.divider()
    st.header("🎯 Final AI Answer")

    # 1. Gather the Text-Based Answer
    text_answer = ""
    if manifest.get("step5") and manifest["step5"].get("found_in_text"):
        text_answer = manifest["step5"].get("answer", "")

    # 2. Gather the Visual First-Person Reflection
    visual_reflection = ""
    needs_review = False
    if manifest.get("step9"):
        visual_reflection = manifest["step9"].get("first_person_summary", "")
        needs_review = manifest["step9"].get("needs_human_verification", False)

    # 3. Stitch them together
    final_combined_answer = f"{text_answer}\n\n{visual_reflection}".strip()

    # 4. Display the Final Output
    if final_combined_answer:
        if needs_review:
            # If the AI admitted the drawing is complex, show it in a warning box
            st.warning(f"**{final_combined_answer}**")
            
            # --- NEW: RENDER THE CONTEXT IMAGES ---
            st.markdown("###### 🔍 Visual Context Provided to AI")
            img_col1, img_col2 = st.columns([1, 3]) # Give the floor plan more space
            
            symbol_path = manifest.get("artifacts", {}).get("symbol_png")
            extracted_pages = manifest.get("step6", {}).get("extracted_pages", [])
            
            with img_col1:
                if symbol_path and Path(symbol_path).exists():
                    st.image(symbol_path, caption="Target Symbol", width=120)
            with img_col2:
                # Just grab the first extracted page as a representation of density
                if extracted_pages and Path(extracted_pages[0]).exists():
                    st.image(extracted_pages[0], caption="Sample Floor Plan Density", use_container_width=True)
            # ---------------------------------------
            
        else:
            # If it's a simple drawing and it's confident, show it in a success box
            st.success(f"**{final_combined_answer}**")
    else:
        st.info("The AI could not confidently generate an answer for this query.")

    # 5. Provide the spatial breakdown grounding below the main answer
    if manifest.get("step8"):
        with st.expander("📍 View Spatial Breakdown (Grounding details)"):
            for tile_name, tile_info in manifest["step8"].get("tiles", {}).items():
                if "symbols" in tile_info and tile_info["symbols"]:
                    st.markdown(f"**In {tile_name}:**")
                    for sym in tile_info["symbols"]:
                        flag = "⚠️" if sym.get("needs_human_review") else "✅"
                        st.markdown(f"- {flag} **Location:** {sym.get('relative_location')} (Confidence: {sym.get('confidence')})")
                        st.markdown(f"  *Reasoning:* {sym.get('visual_evidence')}")

    st.divider()
    
    # ---------------------------------------------------------
    # --- SHOW THINKING / BEHIND THE SCENES ---
    # ---------------------------------------------------------
    with st.expander("🧠 Show thinking"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🧭 AI Routing Decision")
            # Display the Routing JSON
            st.json(manifest.get("step2", {}))

        with col2:
            artifacts = manifest.get("artifacts", {})
            
            legend_path = artifacts.get("legend_png")
            symbol_path = artifacts.get("symbol_png")
            
            # Check if files actually exist on disk
            has_legend = legend_path and Path(legend_path).exists()
            has_symbol = symbol_path and Path(symbol_path).exists()
            
            # Only render the header and visuals if they exist
            if has_legend or has_symbol:
                st.subheader("🖼️ Extracted Visual Artifacts")
                if has_legend:
                    st.image(legend_path, caption="Auto-Extracted Legend", use_container_width=True)
                if has_symbol:
                    st.image(symbol_path, caption="Target Symbol Isolated", width=150)
            else:
                st.info("No visual artifacts (legend/symbol crops) were required or found for this query.")

    st.divider()

    with st.expander("🛠️ View Full Pipeline Manifest & Raw Data"):
        st.json(manifest)