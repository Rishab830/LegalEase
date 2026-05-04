import os
import re
from PIL import Image, ImageOps
import pytesseract
from flask import current_app

def perform_ocr(file_path):
    """
    Perform OCR on an image file.
    
    Includes:
    - EXIF orientation correction.
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
            # Handle EXIF orientation (common in smartphone photos)
            img = ImageOps.exif_transpose(img)
            
            # Ensure image is in RGB for better OCR results
            if img.mode != 'RGB':
                img = img.convert('RGB')
                
            # Check DPI and upscale if too low (below 150 DPI)
            dpi = img.info.get('dpi', (72, 72))
            # Some images don't have DPI info, fallback to 72
            current_dpi = max(dpi[0] if isinstance(dpi[0], (int, float)) else 72, 
                              dpi[1] if isinstance(dpi[1], (int, float)) else 72, 
                              1)
            
            # RAM Protection: Only upscale if the total pixel count is relatively low
            # A 300 DPI A4 page is ~8.7 MP. If we are already above 10MP, don't upscale regardless of DPI metadata.
            current_mp = (img.width * img.height) / 1_000_000
            
            if current_dpi < 150 and current_mp < 10:
                # Target at least 300 DPI for reliable OCR
                scale_factor = 300 / current_dpi
                # Cap the scale factor to avoid creating astronomical images
                scale_factor = min(scale_factor, 4.0)
                
                new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
                
                # Double check that new size isn't insane (cap at ~25MP)
                if (new_size[0] * new_size[1]) < 25_000_000:
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    current_app.logger.info(f"Image upscaled by factor {scale_factor:.2f} due to low DPI ({current_dpi}).")
                else:
                    current_app.logger.warning(f"Upscaling skipped: resulting image would be too large for RAM.")

            # Orientation and Script Detection (OSD) as fallback/supplement to EXIF
            try:
                osd = pytesseract.image_to_osd(img)
                # Parse OSD output: 'Orientation in degrees: 270'
                for line in osd.split('\n'):
                    if 'Orientation in degrees:' in line:
                        angle_match = re.search(r'\d+', line)
                        if angle_match:
                            angle = int(angle_match.group())
                            if angle != 0:
                                img = img.rotate(-angle, expand=True)
                                current_app.logger.info(f"Image rotation corrected by {-angle} degrees via OSD.")
                        break
            except Exception as e:
                # OSD can fail for blank pages or images with too little text
                current_app.logger.debug(f"Orientation detection (OSD) skipped: {str(e)}")

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
