# Technical Walkthrough: quad-scrape Repository

## 1. Project Setup

This section details the necessary steps to set up the development environment and install all required dependencies for the `quad-scrape` project.

### Prerequisites

- **Python:** 3.8 - 3.12
- **Poetry:** A dependency management tool. Installation instructions can be found at [python-poetry.org](https://python-poetry.org/).
- **Optional System Tools:**
    - **Tesseract OCR:** Required for optical character recognition from images and PDFs. Ensure `tesseract.exe` is on your system's `PATH`.
    - **Poppler:** A PDF rendering library, used as a fallback for PDF processing. Ensure its `bin` directory is on your system's `PATH`.

### Installation Steps

1.  **Lock Dependencies:** It is recommended to lock the dependencies to ensure a consistent environment. Open a PowerShell terminal in the project root and run:
    ```powershell
    py -m poetry lock
    ```

2.  **Install Dependencies:** Install the project's dependencies using Poetry:
    ```powershell
    py -m poetry install --no-root
    ```
    This command installs all dependencies specified in the `pyproject.toml` and `poetry.lock` files into a virtual environment managed by Poetry.

## 2. Execution & Entry Points

The `quad-scrape` pipeline is executed as a series of command-line operations. The primary entry point is through the `combo` Python module.

### Main Commands

The core components of the pipeline are invoked using the following structure:

```powershell
py -m poetry run python -m combo <command> [args]
```

Where `<command>` is one of the following pipeline stages:

-   `normalize`: Segments text into sentences and chunks.
-   `validate`: Validates the structure and integrity of normalized files.
-   `embed`: Generates vector embeddings for text chunks.
-   `er`: Performs entity and relation extraction.
-   `coref`: Resolves within-document coreferences.
-   `link`: Links entities across documents to a canonical registry.

### Poetry Scripts

While the `pyproject.toml` file defines script aliases like `combo-normalize`, `combo-validate`, etc., some of these may not be up-to-date with the current file structure. The most reliable method of execution is using the `python -m combo <command>` pattern.

## 3. Data Flow Pipeline

The `quad-scrape` project processes data through a multi-stage pipeline. Each stage takes the output of the previous one as its input, progressively transforming raw data into a structured format.

### Step A: Normalize & Validate

#### **Normalize**

-   **Purpose:** To take raw, extracted JSON data and segment it into a structured format of sentences and chunks.
-   **Command:**
    ```powershell
    py -m poetry run python -m combo normalize <input_directory> --out <output_directory>
    ```
-   **Inputs:** A directory containing JSON files with extracted text. Each file can contain a single JSON object or a list of objects. The text is expected to be in a field like `"pages"` or `"text"`.
-   **Key Files:** `src/combo/normalize/segment.py` contains the core logic for sentence and chunk segmentation. The entry point is the `main` function within this file, dispatched from `src/combo/__main__.py`.
-   **Outputs:** A directory (`<output_directory>`) containing `*.normalized.json` files. Each file represents a single document and contains:
    -   `meta`: Information about the normalization process.
    -   `doc`: Document-level metadata.
    -   `sentences`: A list of all extracted sentences with their text and character offsets.
    -   `chunks`: A list of text chunks, where each chunk is a sequence of sentences.
    -   `images`: A list of image metadata.

#### **Validate**

-   **Purpose:** To ensure that the `*.normalized.json` files adhere to the expected schema and data integrity rules.
-   **Command:**
    ```powershell
    py -m poetry run python -m combo validate <normalized_directory>
    ```
-   **Inputs:** The directory containing the `*.normalized.json` files produced by the `normalize` step.
-   **Key Files:** `src/combo/normalize/validate.py` contains the schema definition and validation logic. The entry point is the `main` function in this file, dispatched from `src/combo/__main__.py`.
-   **Outputs:** A summary printed to the console indicating the number of validated files and any failures. The process exits with a non-zero code if validation failures are found.
-   **Handoff:** The validated `*.normalized.json` files are ready for the next stage of the pipeline.

### Step B: Chunk & Embed

#### **Chunk (Deep)**

-   **Purpose:** Before embedding, a helper script `make_chunks_deep.py` is used to create JSONL files from the normalized JSONs. This script performs a deep search for all string content within the normalized files and chunks it.
-   **Command:**
    ```powershell
    py ./make_chunks_deep.py
    ```
-   **Inputs:** The `tmp_norm` directory (or as configured in the script) containing `*.normalized.json` files.
-   **Key Files:** `make_chunks_deep.py`.
-   **Outputs:** The `tmp_chunks` directory containing `*.jsonl` files. Each line in a file is a JSON object representing a text chunk.

#### **Embed**

-   **Purpose:** To convert the text chunks into numerical vector embeddings.
-   **Command:**
    ```powershell
    py -m poetry run python -m combo embed <chunks_directory> --out <embeddings_directory>
    ```
-   **Inputs:** A directory (`tmp_chunks`) containing the `*.jsonl` files of text chunks.
-   **Key Files:** `src/combo/embed/cli.py` and `src/combo/embed/api.py`. The `cli.py` file handles argument parsing and orchestrates the embedding process.
-   **Outputs:** An embeddings directory (`<embeddings_directory>`) containing:
    -   `*.embedded.jsonl`: Files with the vector embeddings for each chunk.
    -   `manifest.json`: A summary of the embedding run.
    -   `_reports/run_report.json`: A report with error counts and other notes.
-   **Handoff:** The `*.embedded.jsonl` files, along with the original normalized data, are used in the entity recognition step.

### Step C: Entity Recognition (ER) and Coreference Resolution (Coref)

#### **Entity Recognition (ER)**

-   **Purpose:** To identify and extract named entities (e.g., persons, organizations) from the text.
-   **Command:**
    ```powershell
    py -m poetry run python -m combo er <embeddings_directory> --normalized-dir <normalized_directory> --out <er_directory>
    ```
-   **Inputs:**
    -   The embeddings directory from the previous step.
    -   The directory of normalized JSON files to access the original chunk text.
-   **Key Files:** `src/combo/er/cli.py` and `src/combo/er/api.py`.
-   **Outputs:** An entity recognition directory (`<er_directory>`) containing:
    -   `*.entities.jsonl`: Files with the extracted entities.
    -   `*.rels.jsonl`: Files with extracted relationships between entities.
    -   `manifest.json`: A summary of the ER run.
-   **Handoff:** The `*.entities.jsonl` files are used as input for coreference resolution.

#### **Coreference Resolution (Coref)**

-   **Purpose:** To identify and link mentions that refer to the same entity within a single document.
-   **Command:**
    ```powershell
    py -m poetry run python -m combo coref <er_directory> --out <coref_directory>
    ```
-   **Inputs:** The directory of `*.entities.jsonl` files produced by the ER step.
-   **Key Files:** `src/combo/coref/cli.py` and `src/combo/coref/within_doc.py`.
-   **Outputs:** A coreference directory (`<coref_directory>`) containing:
    -   `*.entities.jsonl`: The original entity files, now augmented with coreference information (e.g., `antecedent_mention_id`).
    -   `*.coref_chains.jsonl`: Files describing the resolved coreference chains.
    -   `_reports/run_report.json`: A summary of the coreference resolution process.
-   **Handoff:** The coreference-augmented `*.entities.jsonl` files are used for cross-document entity linking.

### Step D: Link Entities

-   **Purpose:** To link entities across multiple documents to a canonical entity in a central registry.
-   **Command:**
    ```powershell
    py -m poetry run python -m combo link <coref_directory> --registry <registry.sqlite> --out <linked_directory>
    ```
-   **Inputs:**
    -   The directory of coreference-augmented `*.entities.jsonl` files.
    -   A path to an SQLite database file to be used as the entity registry.
-   **Key Files:** `src/combo/link/linker.py` and `src/combo/link/registry.py`.
-   **Outputs:** A linked directory (`<linked_directory>`) containing:
    -   `linked.entities.jsonl`: A file where each line represents a canonical entity, linking together all its mentions across documents.
    -   `_reports/run_report.json`: A summary of the linking process.

## 4. Final Summary

The `quad-scrape` repository provides a powerful pipeline for extracting, structuring, and linking information from unstructured documents. By following the steps outlined in this walkthrough, a new developer can set up the environment, run the entire data processing pipeline, and understand the flow of data through each component. The modular design allows for each step to be inspected and customized, making it an extensible platform for knowledge graph construction.
