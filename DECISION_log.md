# Decision Log

---

# Day 1 — Initial Architecture and First Failures

## Initial Approach

My first instinct was to keep the system as simple as possible:

```text
PDF → Query → VLM → Answer
```

After the first round of testing, it became immediately clear that this approach was not reliable. The VLM was producing hallucinations, incorrect counts, and poor grounding.

Rather than continuing to tune prompts, I decided to break the problem into smaller stages.

---

## Decision: Extract the Legend First

While inspecting the sample PDFs, I noticed that the legend acts as the key to understanding the rest of the drawing.

My first attempt was to build a custom OpenCV-based legend extraction pipeline using text anchors and layout heuristics. The approach worked surprisingly well on the provided examples.

However, it was heavily tuned to only two PDFs.

### Decision

Abandon the custom legend extraction approach in favor of a more general solution.

### Reasoning

A solution that works on only two documents is unlikely to generalize.

---

## Decision: Locate Legends Through Text Extraction

Instead of relying on image processing, I extracted PDF text and searched for keywords such as:

* LEGEND
* ABBREVIATIONS
* GENERAL NOTES
* FLAG NOTES

This worked successfully on Image 2.

The next challenge became locating the actual legend region on the page.

---

## Challenge: Finding Legend Bounding Boxes

A significant amount of Day 1 was spent trying to determine reliable legend coordinates.

At this stage I had text extraction working, but I did not yet have a reliable method for obtaining precise legend bounding boxes.

This became the primary blocker.

---

# Day 2 — VLM-Assisted Localization

## Decision: Use Whole Legend Pages

Since reliable legend bounding boxes were not available, I temporarily switched to using the entire page containing the legend.

This worked better than expected.

However, Image 1 introduced a new challenge:

* The legend appeared visually embedded inside the drawing.
* Legend contents appeared to be image-based.
* Text extraction was unable to recover legend information.

---

## Decision: Use a VLM for Legend Localization

I experimented with VLM-generated bounding boxes.

Initial results were noisy, but an important pattern emerged:

### Observation

The VLM rarely produced completely incorrect coordinates.

Instead, it frequently predicted regions close to the correct location.

### Decision

Apply coordinate scaling and generous padding around predicted boxes.

This significantly increased localization reliability.

---

## Observation: PDF Crops Remain Sharp

While evaluating the crops, I noticed that zoomed PDF regions remained extremely sharp.

The diagrams were largely vector-based.

This insight suggested that future diagram-level extraction could be practical.

Although promising, the idea required additional R&D and was deferred.

---

# Symbol Extraction

Once legend extraction was working, the next objective became symbol extraction.

---

## Attempt 1: Text-Based Symbol Localization

Using the legend page and extracted text, I attempted to locate symbols through nearby text coordinates.

The approach worked well for Image 2.

It failed on Image 1 because the required text was not available.

---

## Attempt 2: VLM-Assisted Symbol Localization

I introduced a second VLM call specifically for symbol extraction.

### Observation

The model was approximately 80% accurate.

Most failures involved selecting neighboring symbols.

### Decision

Increase crop padding to include surrounding entries.

This provided additional context and significantly improved reliability.

---

# Query Routing Architecture

At this point I realized that not every question required image reasoning.

Many questions could be answered directly from extracted text.

---

## Decision: Introduce a Routing Layer

A routing stage was added to classify user intent.

Examples:

* Counting
* Explanation
* Summarization
* Abbreviation lookup

The original implementation used Mistral 7B.

---

## Challenge: Structured Outputs

Mistral frequently failed to produce valid JSON.

I explored:

* Local Ollama deployment
* OpenAI-compatible APIs
* Structured output enforcement

Although workable, latency became unacceptable.

### Decision

Replace Mistral routing with a lightweight Gemini Flash model.

The improvement in reliability and response time justified the change.

---

# Text-Only Question Optimization

To avoid unnecessary image processing:

1. Extract all document text once.
2. Store it in a text file.
3. Route text-only questions directly to an LLM.

This reduced processing cost and execution time.

---

# Counting Pipeline

Counting questions required additional reasoning.

Initially I attempted to search the entire PDF using the extracted symbol.

This was computationally expensive and frequently hallucinated.

---

## Decision: Page-Level Search Routing

The routing stage was extended to answer:

* What should be counted?
* Which pages are likely relevant?

The mapping information already existed in extracted text.

This proved highly reliable.

The VLM now only processes relevant pages.

---

# VLM Hallucination Analysis

Several recurring failure modes were identified.

## Problem 1

Entire PDF pages contain:

* Large white regions
* Notes
* Flags
* Unrelated content

These distract the model.

## Problem 2

Large engineering sheets become compressed before VLM processing.

This reduces visual fidelity.

## Problem 3

Prompts remained too generic.

---

# Decision: Tile-Based Processing

Instead of sending entire pages:

1. Split pages into tiles.
2. Process tiles independently.

### Challenge

Symbols may cross tile boundaries.

### Solution

Use overlapping tiles.

---

## Grid Experiments

### 2×2

Insufficient.

### 3×3

Improved.

### 4×4

~80% accuracy.

### 5×5

~88% accuracy.

However, API cost and latency increased substantially.

### Decision

Use 4×4 as the default compromise.

---

# Day 3 — Diagram Extraction

A new idea emerged:

Instead of tiling entire pages, isolate the actual diagram first.

This should:

* Reduce hallucinations
* Improve counting accuracy
* Reduce wasted visual context

---

## Proposed Improvement: Coordinate-Based Symbol Cropping

If symbol text exists in extracted PDF text:

1. Obtain text coordinates.
2. Apply generous padding.
3. Include neighboring labels.
4. Crop directly.

This removes the need for VLM-based symbol localization.

Expected reliability is significantly higher.

---

## Proposed Improvement: Selective Verification

Instead of validating every answer:

Only trigger a second verification pass for uncertain queries.

Examples:

* Count
* How many
* Where is
* Locate

This reduces API cost while preserving accuracy.

---

# Diagram Extraction Experiments

I initially explored vector-line grouping and edge detection.

The concept appeared promising but required substantial implementation effort.

Due to time constraints it was placed on hold.

---

## Decision: Switch to OpenCV-Based Diagram Extraction

After several iterations, OpenCV successfully extracted:

* High-quality diagrams
* Reduced legend contamination
* Meaningful diagram regions

The resulting crops worked substantially better for VLM counting.

---

# Current Results

For Image 2 Question 1:

Ground truth:

```text
44–45 Air Swirl Diffusers
```

Model output:

```text
41 Air Swirl Diffusers
```

This is not perfect, but represents a substantial improvement over earlier approaches.

---

# Grounding Challenges

Grounding remains significantly harder on Image 1.

Reasons:

* Mixed vector and raster content
* Missing text extraction
* Embedded legends

Image 2 is considerably easier because text extraction succeeds.

---

# Current Work

1. Improve grounding for Image 1.
2. Add user confirmation after legend extraction.
3. Add user confirmation after symbol extraction.
4. Retry failed extractions automatically.
5. Fall back to using the entire legend when symbol extraction fails.

Due to time constraints, these ideas are currently paused despite promising initial results.
