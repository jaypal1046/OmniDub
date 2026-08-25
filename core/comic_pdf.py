import os
import glob
from PIL import Image

def extract_pdf_pages(pdf_path, output_dir):
    """
    Extracts pages from a PDF file as high-quality JPEG images.
    Returns a list of filepaths to the extracted images.
    """
    os.makedirs(output_dir, exist_ok=True)
    image_paths = []

    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        print(f"📖 Reading PDF: {os.path.basename(pdf_path)} ({len(doc)} pages)...")
        
        for i in range(len(doc)):
            page = doc.load_page(i)
            # Render page at 2x resolution (150-200 DPI equivalent) for sharp text/panels
            zoom = 2.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            img_filename = f"page_{i+1:03d}.jpg"
            img_path = os.path.join(output_dir, img_filename)
            pix.save(img_path)
            image_paths.append(img_path)
        doc.close()
        return image_paths

    except ImportError:
        print("⚠️ PyMuPDF (fitz) not installed. Checking for Pillow PDF fallback...")
        try:
            with Image.open(pdf_path) as img:
                i = 0
                while True:
                    img_filename = f"page_{i+1:03d}.jpg"
                    img_path = os.path.join(output_dir, img_filename)
                    img.convert("RGB").save(img_path, "JPEG")
                    image_paths.append(img_path)
                    i += 1
                    img.seek(i)
        except Exception as e:
            print(f"❌ Error extracting PDF pages: {e}")
            return []

def load_comic_images(input_path, temp_dir):
    """
    Given a path to a PDF or a directory of images, returns a sorted list of image filepaths.
    """
    if os.path.isfile(input_path) and input_path.lower().endswith(".pdf"):
        pages_dir = os.path.join(temp_dir, "extracted_pages")
        return extract_pdf_pages(input_path, pages_dir)
    elif os.path.isdir(input_path):
        search_dir = input_path
        if os.path.exists(os.path.join(input_path, "images")) and os.path.isdir(os.path.join(input_path, "images")):
            search_dir = os.path.join(input_path, "images")

        valid_exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
        found_files = []
        for root, _, files in os.walk(search_dir):
            for f in files:
                if any(f.lower().endswith(ext) for ext in valid_exts):
                    found_files.append(os.path.join(root, f))

        import re
        def natural_sort_key(s):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]

        found_files = sorted(list(set(found_files)), key=natural_sort_key)
        print(f"📁 Loaded {len(found_files)} comic page images from directory ({search_dir}).")
        return found_files
    else:
        raise ValueError(f"Input path '{input_path}' is neither a PDF file nor a directory of images.")
