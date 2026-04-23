import sys
import os
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

def generate_pdf(input_file, output_file):
    try:
        with sync_playwright() as p:
            # Use stable Chromium args
            browser = p.chromium.launch(args=[
                '--no-sandbox', 
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ])
            
            page = browser.new_page()
            
            # Using pathlib's as_uri() is the most robust cross-platform way to generate file:// URLs
            file_url = Path(input_file).resolve().as_uri()
            page.goto(file_url, wait_until="load")
            
            # Small wait for any JS/fonts
            page.wait_for_timeout(2000)
            
            # Generate PDF
            page.pdf(
                path=output_file,
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                scale=0.9
            )
            
            browser.close()
            return True
    except Exception as e:
        print(f"ERROR: {str(e)}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python pdf_generator.py <input_html> <output_pdf>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    if generate_pdf(input_file, output_file):
        sys.exit(0)
    else:
        sys.exit(1)
