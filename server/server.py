# server/server.py

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
import requests
import fitz  # PyMuPDF
import os
from datetime import datetime

app = FastAPI(title="DocuSage API", version="2.0")

# Enhanced CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "gemma3:12b-it-q4_K_M")

def extract_text_from_pdf(file_bytes):
    """Extract text from PDF with better error handling"""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page_num, page in enumerate(doc):
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")

# Root endpoint to serve the web UI
@app.get("/")
async def serve_ui():
    """Serve the web UI"""
    ui_path = os.path.join(os.path.dirname(__file__), "..", "web", "index.html")
    if os.path.exists(ui_path):
        return FileResponse(ui_path)
    else:
        return {"message": "DocuSage API - Use /docs for API documentation"}

# Mount the web directory as static files
web_path = os.path.join(os.path.dirname(__file__), "..", "web")
if os.path.exists(web_path):
    app.mount("/web", StaticFiles(directory=web_path), name="web")

@app.get("/health")
async def health_check():
    """Health check endpoint for UI status monitoring"""
    try:
        # Check if Ollama is accessible
        response = requests.get(f"{OLLAMA_URL.replace('/api/generate', '')}/api/tags", timeout=5)
        ollama_status = "online" if response.status_code == 200 else "offline"
    except:
        ollama_status = "offline"
    
    return {
        "status": "online",
        "ollama": ollama_status,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/summarize")
async def summarize(
    file: UploadFile = File(...),
    length: str = Form(default="standard"),
    language: str = Form(default="en")
):
    """Enhanced summarization endpoint with options"""
    content = await file.read()
    
    # Validate file size (max 10MB)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")

    # Handle different file types
    if file.filename.endswith(".pdf"):
        text = extract_text_from_pdf(content)
    elif file.filename.endswith(".txt"):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            # Try different encodings
            for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise HTTPException(status_code=400, detail="Unable to decode text file. Please ensure it's a valid text file.")
    else:
        raise HTTPException(status_code=415, detail="Unsupported file type. Only .txt and .pdf files are allowed.")

    # Validate text content
    if not text.strip():
        raise HTTPException(status_code=400, detail="The document appears to be empty.")

    # Customize prompt based on options
    length_instructions = {
        "brief": "Provide a very brief summary in 2-3 sentences.",
        "standard": "Provide a comprehensive summary.",
        "detailed": "Provide a detailed summary with key points and important details."
    }
    
    language_instructions = {
        "en": "in English",
        "es": "in Spanish",
        "fr": "in French",
        "de": "in German",
        "ja": "in Japanese",
        "zh": "in Chinese"
    }
    
    prompt = f"""
    {length_instructions.get(length, length_instructions['standard'])}
    Summarize the following document {language_instructions.get(language, 'in English')}:
    
    {text[:5000]}  # Limit text to prevent token overflow
    """

    # Call Ollama with enhanced error handling
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        summary = result.get("response", "No summary returned.")
        
        # Log summary generation for monitoring
        print(f"Generated summary for {file.filename} ({len(text)} chars) in {language}")
        
        return {
            "summary": summary,
            "metadata": {
                "original_filename": file.filename,
                "original_size": len(content),
                "text_length": len(text),
                "summary_length": len(summary),
                "language": language,
                "length_option": length,
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Request timed out. The document might be too large.")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with Ollama: {str(e)}")

@app.post("/batch_summarize")
async def batch_summarize(files: list[UploadFile] = File(...)):
    """Process multiple files at once"""
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files allowed per batch.")
    
    results = []
    for file in files:
        try:
            # Process each file
            result = await summarize(file)
            results.append({
                "filename": file.filename,
                "success": True,
                "summary": result["summary"],
                "metadata": result["metadata"]
            })
        except Exception as e:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    return {"results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)