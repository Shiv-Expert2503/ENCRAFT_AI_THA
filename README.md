# Encraft AI – MEP Drawing Interpreter

An automated web application for interpreting Mechanical, Electrical, and Plumbing (MEP) construction drawings. The system combines document understanding, visual-language models (VLMs), vector-based PDF analysis, and grounding techniques to answer natural language questions and provide visual evidence for its responses.

The solution is designed to operate on complex engineering drawings containing legends, abbreviations, symbols, schedules, notes, and large-scale diagram layouts.

---

## Features

* Natural language querying over MEP drawings
* Automatic legend and abbreviation discovery
* Symbol extraction and matching
* Query routing based on question type
* Visual grounding with highlighted evidence
* Diagram-aware counting workflows
* Tile-based VLM processing for large engineering sheets
* Hybrid text + vision reasoning pipeline
* Streamlit-based interactive interface

---

## Quick Start

### Prerequisites

* Docker
* Docker Compose
* Gemini API Key

---

### 1. Clone the Repository

```bash
git clone https://github.com/Shiv-Expert2503/ENCRAFT_AI_THA.git
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_api_key_here
```

---

### 3. Launch the Application

```bash
docker compose up --build
```

---

### 4. Open the Application

Navigate to:

```text
http://localhost:8501
```

---

# System Architecture

The pipeline combines deterministic PDF analysis with VLM-based reasoning.

```text
User Query
     │
     ▼
Query Router
     │
     ├── Text-Based Questions
     │         │
     │         ▼
     │    Extracted PDF Text
     │         │
     │         ▼
     │      LLM Answer
     │
     └── Vision-Based Questions
               │
               ▼
      Legend & Symbol Extraction
               │
               ▼
        Diagram Localization
               │
               ▼
          Tile Generation
               │
               ▼
             VLM
               │
               ▼
      Grounded Final Answer
```

---

# Core Components

## User Interface

**Framework:** Streamlit

Provides:

* PDF upload
* Query interface
* Evidence visualization
* Grounding previews
* Intermediate extraction inspection

---

## Query Routing

**Model:** Gemini 2.5 Flash

Classifies incoming questions into categories such as:

* Counting
* Lookup
* Summarization
* Abbreviation expansion
* Explanation

This allows the system to avoid expensive visual processing when text alone is sufficient.

---

## Text Processing

**Libraries:**

* PyMuPDF (`fitz`)
* JSON-based document inventory generation

Capabilities:

* Full-text extraction
* Legend discovery
* Abbreviation discovery
* Page-level metadata indexing
* Candidate page selection

---

## Legend Extraction

The system first identifies legend regions using a combination of:

* Text-anchor detection
* PDF layout analysis
* VLM-assisted localization (fallback)

Legend extraction serves as the foundation for downstream symbol reasoning.

---

## Symbol Extraction

Symbols are extracted using:

1. Text-coordinate matching (preferred)
2. Legend-region cropping
3. VLM-assisted symbol localization (fallback)

Additional padding and context-aware cropping are used to improve robustness.

---

## Diagram Extraction

Large engineering drawings often contain:

* Notes
* White space
* Schedules
* Non-relevant annotations

To reduce hallucinations, the system isolates diagram regions before VLM processing using image-processing techniques and layout heuristics.

---

## Tile-Based Visual Analysis

Large-format engineering sheets cannot reliably be processed as a single image.

The pipeline:

1. Extracts relevant diagram regions
2. Splits them into overlapping tiles
3. Performs localized VLM analysis
4. Aggregates results

This significantly improves counting accuracy and symbol detection performance.

---

## Grounding Engine

**Libraries:**

* PyMuPDF
* Pillow

Used for:

* Coordinate extraction
* Bounding box rendering
* Evidence highlighting
* Exact-match vector grounding

For text-based answers, evidence is located directly in the source PDF and visually highlighted.

---

# Technology Stack

| Component                | Technology       |
| ------------------------ | ---------------- |
| Frontend                 | Streamlit        |
| Vision-Language Model    | Gemini 2.5 Flash |
| Routing & Classification | Gemini 2.5 Flash |
| PDF Processing           | PyMuPDF (fitz)   |
| Image Processing         | Pillow, OpenCV   |
| Containerization         | Docker           |
| Data Storage             | JSON Artifacts   |

---

# Design Philosophy

Instead of relying entirely on a Vision-Language Model, the system follows a hybrid approach:

* Use deterministic extraction whenever possible
* Use VLM reasoning only where required
* Ground answers back to source evidence
* Minimize hallucinations through targeted context selection
* Reduce API cost through routing and preprocessing

This approach improves reliability on complex engineering drawings while maintaining reasonable performance and cost.
