import os
from PIL import Image
import pytesseract
from flask import current_app

def perform_ocr(file_path):
    """
    Perform OCR on an image file.
    
    Includes:
    - DPI check and automatic upscaling for low-resolution images (< 150 DPI).
    - Orientation detection and correction (OSD).
    - Raw text extraction using Tesseract.
    
    Returns:
        tuple: (raw_text, status)
    """
    try:
        # Configure Tesseract path
        tesseract_cmd = current_app.config.get('TESSERACT_CMD', 'tesseract')
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
        # Open the image file
        with Image.open(file_path) as img:
            # Ensure image is in RGB for better OCR results
            if img.mode != 'RGB':
                img = img.convert('RGB')
                
            # Check DPI and upscale if too low (below 150 DPI)
            dpi = img.info.get('dpi', (72, 72))
            # Some images don't have DPI info, fallback to 72
            current_dpi = max(dpi[0], dpi[1], 1)
            
            if current_dpi < 150:
                # Target at least 300 DPI for reliable OCR
                scale_factor = 300 / current_dpi
                new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                current_app.logger.info(f"Image upscaled by factor {scale_factor:.2f} due to low DPI ({current_dpi}).")

            # Orientation and Script Detection (OSD)
            try:
                osd = pytesseract.image_to_osd(img)
                # Parse OSD output: 'Orientation in degrees: 270'
                for line in osd.split('\n'):
                    if 'Orientation in degrees:' in line:
                        angle = int(line.split(':')[-1].strip())
                        if angle != 0:
                            img = img.rotate(-angle, expand=True)
                            current_app.logger.info(f"Image rotation corrected by {-angle} degrees.")
                        break
            except (pytesseract.TesseractError, Exception) as e:
                # OSD can fail for blank pages or images with too little text
                current_app.logger.warning(f"Orientation detection (OSD) skipped: {str(e)}")

            # Extract raw text
            raw_text = pytesseract.image_to_string(img)
            
            if not raw_text or not raw_text.strip():
                return "", "ocr_empty"
                
            return raw_text.strip(), "ocr_complete"
            
    except FileNotFoundError:
        current_app.logger.error(f"Image file not found: {file_path}")
        return "", "ocr_failed"
    except Exception as e:
        current_app.logger.error(f"OCR process failed: {str(e)}")
        return "", "ocr_failed"
