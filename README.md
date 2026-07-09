# Local File Organizer: AI File Management Run Entirely on Your Device, Privacy Assured

Tired of digital clutter? Overwhelmed by disorganized files scattered across your computer? Let AI do the heavy lifting! The Local File Organizer is your personal organizing assistant, using cutting-edge AI to bring order to your file chaos - all while respecting your privacy.

## How It Works 💡

Before:

```
/home/user/messy_documents/
├── IMG_20230515_140322.jpg
├── IMG_20230516_083045.jpg
├── IMG_20230517_192130.jpg
├── budget_2023.xlsx
├── meeting_notes_05152023.txt
├── project_proposal_draft.docx
├── random_thoughts.txt
├── recipe_chocolate_cake.pdf
├── scan0001.pdf
├── vacation_itinerary.docx
└── work_presentation.pptx

0 directories, 11 files
```

After:

```
/home/user/organized_documents/
├── Financial
│   └── 2023_Budget_Spreadsheet.xlsx
├── Food_and_Recipes
│   └── Chocolate_Cake_Recipe.pdf
├── Meetings_and_Notes
│   └── Team_Meeting_Notes_May_15_2023.txt
├── Personal
│   └── Random_Thoughts_and_Ideas.txt
├── Photos
│   ├── Cityscape_Sunset_May_17_2023.jpg
│   ├── Morning_Coffee_Shop_May_16_2023.jpg
│   └── Office_Team_Lunch_May_15_2023.jpg
├── Travel
│   └── Summer_Vacation_Itinerary_2023.docx
└── Work
    ├── Project_X_Proposal_Draft.docx
    ├── Quarterly_Sales_Report.pdf
    └── Marketing_Strategy_Presentation.pptx

7 directories, 11 files
```

## Updates 🚀

**[2024/09] v0.0.2**:
* Featured by [Nexa Gallery](https://nexaai.com/gallery) and [Nexa SDK Cookbook](https://github.com/NexaAI/nexa-sdk/tree/main/examples)!
* Dry Run Mode: check sorting results before committing changes
* Silent Mode: save all logs to a txt file for quieter operation
* Added file support:  `.md`, .`excel`, `.ppt`, and `.csv` 
* Three sorting options: by content, by date, and by type
* The default text model is now [Llama3.2 3B](https://nexaai.com/meta/Llama3.2-3B-Instruct/gguf-q3_K_M/file)
* Improved CLI interaction experience
* Added real-time progress bar for file analysis

Please update the project by deleting the original project folder and reinstalling the requirements. Refer to the installation guide from Step 4.


## Roadmap 📅

- [ ] Copilot Mode: chat with AI to tell AI how you want to sort the file (ie. read and rename all the PDFs)
- [ ] Change models with CLI 
- [ ] ebook format support
- [ ] audio file support
- [ ] video file support
- [ ] Implement best practices like Johnny Decimal
- [ ] Check file duplication
- [ ] Dockerfile for easier installation
- [ ] People from [Nexa](https://github.com/NexaAI/nexa-sdk) is helping me to make executables for macOS, Linux and Windows

## What It Does 🔍

This intelligent file organizer harnesses the power of advanced AI models, including language models (LMs) and vision-language models (VLMs), to automate the process of organizing files by:


* Scanning a specified input directory for files.
* Content Understanding: 
  - **Textual Analysis**: Uses [Llama3.2 3B](https://ollama.com/library/llama3.2) (served via Ollama) to analyze and summarize text-based content, generating relevant descriptions and filenames.
  - **Visual Content Analysis**: Uses [LLaVA 7B](https://ollama.com/library/llava), based on Vicuna-7B, to interpret visual files such as images, providing context-aware categorization and descriptions.

* Understanding the content of your files (text, images, and more) to generate relevant descriptions, folder names, and filenames.
* Organizing the files into a new directory structure based on the generated metadata.

The best part? All AI processing happens 100% on your local device using [Ollama](https://ollama.com). No internet connection required after the initial model download, no data leaves your computer, and no AI API is needed - keeping your files completely private and secure.


## Supported File Types 📁

- **Images:** `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`
- **Text Files:** `.txt`, `.docx`, `.md`
- **Spreadsheets:** `.xlsx`, `.csv`
- **Presentations:** `.ppt`, `.pptx`
- **PDFs:** `.pdf`

## Prerequisites 💻

- **Operating System:** Compatible with Windows, macOS, and Linux.
- **Python Version:** Python 3.12
- **Ollama:** Used to run the local text and vision-language models (native install or Docker).
- **Git:** For cloning the repository (or you can download the code as a ZIP file).

> **Note (2026 update):** This project originally ran on the Nexa SDK. Nexa AI was acquired by
> Qualcomm and its SDK was rebranded as GenieX, which only targets Qualcomm Snapdragon/ARM64
> hardware — it no longer works on generic x86_64 machines, and the legacy `nexaai` PyPI package's
> installer is broken (its binary download now returns `403 Forbidden`). This fork instead uses
> [Ollama](https://ollama.com) to run the local models, which works on any CPU (and GPU, if
> available) on Windows, macOS, and Linux.

## Installation 🛠

### 1. Install Python

Before installing the Local File Organizer, make sure you have Python installed on your system. We recommend using Python 3.12 or later.

You can download Python from [the official website](https://www.python.org/downloads/).

Follow the installation instructions for your operating system.

### 2. Clone the Repository

Clone this repository to your local machine using Git:

```zsh
git clone https://github.com/QiuYannnn/Local-File-Organizer.git
```

Or download the repository as a ZIP file and extract it to your desired location.

### 3. Set Up the Python Environment

Create a virtual environment with Python 3.12:

```zsh
cd path/to/Local-File-Organizer
python3 -m venv venv
```

Activate the environment:

```zsh
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows
```

### 4. Install and Run Ollama

Install Ollama natively (see [ollama.com/download](https://ollama.com/download)), or run it via Docker:

```zsh
docker run -d --name ollama -v ollama:/root/.ollama -p 11434:11434 --restart unless-stopped ollama/ollama
```

Then pull the models this project uses:

```zsh
ollama pull llama3.2:3b
ollama pull llava:7b
```

(If you started Ollama via Docker, prefix these with `docker exec ollama`.)

### 5. Install Dependencies

1. Ensure you are in the project directory:
   ```zsh
   cd path/to/Local-File-Organizer
   ```
   Replace `path/to/Local-File-Organizer` with the actual path where you cloned or extracted the project.

2. Install the required dependencies:
   ```zsh
   pip install -r requirements.txt
   ```

**Note:** If you encounter issues with any packages, install them individually:

```zsh
pip install ollama Pillow pytesseract PyMuPDF python-docx
```

With the environment activated and dependencies installed, run the script using:

### 6. Running the Script🎉
```zsh
python main.py
```

## Notes

- **Models:**
  - The script uses Ollama-served `llama3.2:3b` (text) and `llava:7b` (vision) models via the
    `OllamaTextInference`/`OllamaVLMInference` classes in `ollama_inference.py`.
  - Ollama must be running (natively or via Docker) and reachable at `http://localhost:11434`
    before starting `main.py`.
  - You can swap in any other Ollama-compatible model by changing `model_path`/`model_path_text`
    in `initialize_models()` in `main.py`, as long as you `ollama pull` it first.


- **Dependencies:**
  - **pytesseract:** Requires Tesseract OCR installed on your system.
    - **macOS:** `brew install tesseract`
    - **Ubuntu/Linux:** `sudo apt-get install tesseract-ocr`
    - **Windows:** Download from [Tesseract OCR Windows Installer](https://github.com/UB-Mannheim/tesseract/wiki)
  - **PyMuPDF (fitz):** Used for reading PDFs.

- **Processing Time:**
  - Processing may take time depending on the number and size of files.
  - The script uses multiprocessing to improve performance.

- **Customizing Prompts:**
  - Prompts live as named constants (`DESCRIPTION_PROMPT`, `FILENAME_PROMPT_TEMPLATE`,
    `FOLDERNAME_PROMPT_TEMPLATE`, etc.) in `image_data_processing.py` (images) and
    `text_data_processing.py` (text documents) — edit them there to change how metadata
    is generated. The shared naming/cleanup logic they both call lives in `ai_metadata.py`.

- **Logging:**
  - All runtime output goes through the `file_organizer` logger (see `logging_setup.py`).
    Every run writes a fresh, timestamped log file under `logs/` (e.g.
    `logs/run_20260709_105121.log`) that always captures full detail, regardless of mode.
    In normal mode, INFO+ messages are also printed to the terminal; in silent mode
    nothing is printed except the log file's path, shown once at startup.

## License

This project is dual-licensed under the MIT License and Apache 2.0 License. You may choose which license you prefer to use for this project.

- See the [MIT License](LICENSE-MIT) for more details.