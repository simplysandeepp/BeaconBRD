import io
import os
from google.cloud import vision
from PIL import Image
import fitz  # PyMuPDF

def _get_vision_client():
    """
    Initializes and returns a Vision API client.
    Checks for credentials and provides helpful error if missing.
    """
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        # If not set via env var, check if a default 'service-account.json' exists in the root
        default_key = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service-account.json")
        if os.path.exists(default_key):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = default_key
        else:
            raise RuntimeError(
                "GCP Credentials not found. Please set GOOGLE_APPLICATION_CREDENTIALS "
                "environment variable or place 'service-account.json' in the backend/ directory."
            )
    return vision.ImageAnnotatorClient()

def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Extracts text from image bytes using Google Cloud Vision API.
    """
    client = _get_vision_client()
    image = vision.Image(content=image_bytes)
    
    # For document-style images, document_text_detection is better than text_detection
    response = client.document_text_detection(image=image)
    
    if response.error.message:
        raise Exception(f"Vision API Error: {response.error.message}")
    
    return response.full_text_annotation.text

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extracts text from PDF bytes by converting pages to images 
    and then using Google Cloud Vision API.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = []
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        # Convert page to image (higher DPI for better OCR)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        
        text = extract_text_from_image(img_bytes)
        full_text.append(text)
        
    doc.close()
    return "\n\n".join(full_text)
