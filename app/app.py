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

    # Create two columns for a clean UI
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🧭 AI Routing Decision")
        # Display the Mistral/Pydantic routing JSON
        st.json(manifest.get("step2", {}))

    with col2:
        st.subheader("🖼️ Extracted Visual Artifacts")
        artifacts = manifest.get("artifacts", {})

        # Safely check and display the legend image if it exists
        legend_path = artifacts.get("legend_png")
        if legend_path and Path(legend_path).exists():
            st.image(
                legend_path, caption="Auto-Extracted Legend", use_container_width=True
            )

        # Safely check and display the specific symbol image if it exists
        symbol_path = artifacts.get("symbol_png")
        if symbol_path and Path(symbol_path).exists():
            st.image(symbol_path, caption="Target Symbol Isolated", width=150)

    st.divider()

    with st.expander("🛠️ View Full Pipeline Manifest & Raw Data"):
        st.json(manifest)
