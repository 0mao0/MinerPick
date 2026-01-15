import os
import uuid
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from config import settings
from parsers import MinerUParser, PyMuPDFParser

# Use absolute paths relative to this script
BASE_DIR = Path(__file__).resolve().parent

# For pip install compatibility, we prefer a local static folder inside the package
STATIC_DIR = BASE_DIR / "static"

app = FastAPI()

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Parsers
PARSERS = {}

if MinerUParser is not None:
    PARSERS["mineru"] = MinerUParser(api_url=settings.mineru_api_url, api_key=settings.mineru_api_key)
    
PARSERS["pymupdf"] = PyMuPDFParser()

def get_unique_filename(directory: Path, filename: str) -> Path:
    """Get a unique filename in the directory by adding a suffix if it already exists."""
    base = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    new_filename = filename
    while (directory / new_filename).exists():
        new_filename = f"{base} ({counter}){suffix}"
        counter += 1
    return directory / new_filename

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/config")
async def get_config():
    """Returns basic server configuration, sanitizing sensitive keys."""
    masked_key = ""
    if settings.mineru_api_key:
        key = settings.mineru_api_key
        if len(key) > 8:
            masked_key = f"{key[:4]}{'*' * (len(key)-8)}{key[-4:]}"
        else:
            masked_key = "*" * len(key)
            
    return {
        "mineru_api_url": settings.mineru_api_url,
        "has_mineru_api_key": bool(settings.mineru_api_key),
        "mineru_api_key_masked": masked_key,
    }

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    task_id = str(uuid.uuid4())
    
    pdf_path = get_unique_filename(settings.input_dir, file.filename)
    final_filename = pdf_path.name

    with open(pdf_path, "wb") as f:
        f.write(await file.read())

    return {
        "task_id": task_id,
        "filename": final_filename,
        "pdf_url": f"/inputs/{final_filename}"
    }

class ConvertRequest(BaseModel):
    task_id: str
    filename: str
    provider: str = "pymupdf"  # Default to pymupdf
    mineru_api_url: Optional[str] = None
    mineru_api_key: Optional[str] = None

@app.post("/api/convert")
async def convert_pdf(request: ConvertRequest):
    task_id = request.task_id
    filename = request.filename
    provider_name = request.provider.lower().strip()
    
    pdf_path = settings.input_dir / filename
    
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    task_output_dir = settings.output_dir / task_id
    os.makedirs(task_output_dir, exist_ok=True)
    
    import shutil
    try:
        shutil.copy2(pdf_path, task_output_dir / filename)
    except Exception as e:
        print(f"Warning: Failed to copy source PDF to output directory: {e}")

    parser = PARSERS.get(provider_name)
    if not parser:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}")

    try:
        # Pass optional overrides to parser if supported
        parse_params = {
            "pdf_path": str(pdf_path),
            "task_result_dir": str(task_output_dir)
        }
        
        if provider_name == "mineru":
            if request.mineru_api_url:
                parse_params["api_url_override"] = request.mineru_api_url
            if request.mineru_api_key:
                parse_params["api_key_override"] = request.mineru_api_key

        # Convert PDF and save results in task_output_dir
        result = await parser.parse(**parse_params)
        
        # Build URLs for the results
        response = {
            "task_id": task_id,
            "provider": provider_name,
            "md_url": f"/results/{task_id}/{result['md_url']}",
            "content_list_url": f"/results/{task_id}/{result['content_list_url']}",
            "content_tables_url": f"/results/{task_id}/{result['content_tables_url']}",
        }
        if result.get("raw_content_list_url"):
            response["raw_content_list_url"] = f"/results/{task_id}/{result['raw_content_list_url']}"
        return response
    except HTTPException as e:
        # Re-raise HTTPExceptions as they already have the correct format
        raise e
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files
app.mount("/results", StaticFiles(directory=settings.output_dir), name="results")
app.mount("/inputs", StaticFiles(directory=settings.input_dir), name="inputs")
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
else:
    print(f"Warning: Frontend static directory not found at {STATIC_DIR}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)

def start():
    """Entry point for pip install execution"""
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
