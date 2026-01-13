import base64
import requests
from pdf2image import convert_from_path
import tempfile
import os
import shutil
import sys
from ollama import Client


OLLAMA_URL = os.environ.get("OLLAMA_URL")
MODEL = os.environ.get("MODEL")
# Por defecto usamos /app/res (montado desde ./res en tu host)
PDF_DIR = os.environ.get("PDF_DIR", "/app/res")
RES_DIR = os.environ.get("RES_DIR", "/app/res")

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def pdf_to_images(pdf_path, dpi=300):
    tmpdir = tempfile.mkdtemp(prefix="pdf_images_")
    pages = convert_from_path(pdf_path, dpi=dpi, output_folder=tmpdir)
    image_paths = []
    for i, page in enumerate(pages):
        img_path = os.path.join(tmpdir, f"page_{i+1}.png")
        page.save(img_path, "PNG")
        image_paths.append(img_path)
    return image_paths, tmpdir

def ocr_images(image_paths, client, timeout=300):
    resp = client.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": "Extraé TODO el texto del documento. Mantené el orden de lectura y respetá saltos de línea.",
            "images": image_paths
        }]
    )
    print(resp)
    message_content = resp.message.content 

    #resp = client.generate(
    #    model=MODEL,
    #    prompt="Extraé TODO el texto del documento. Mantené el orden de lectura y respetá saltos de línea.",
    #    images=image_paths
    #)

    return message_content


def find_first_pdf(dir_path):
    if not os.path.isdir(dir_path):
        return None
    for entry in os.listdir(dir_path):
        if entry.lower().endswith(".pdf"):
            return os.path.join(dir_path, entry)
    return None

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path

if __name__ == "__main__":
    pdf_path = find_first_pdf(PDF_DIR)
    if not pdf_path:
        print(f"No se encontró ningún .pdf en '{PDF_DIR}'. Pon el archivo (ej. documento.pdf) dentro de esa carpeta.", file=sys.stderr)
        sys.exit(1)

    pdf_name = os.path.basename(pdf_path)
    pdf_stem = os.path.splitext(pdf_name)[0]
    out_folder = ensure_dir(os.path.join(RES_DIR, pdf_stem))

    image_paths, tmpdir = pdf_to_images(pdf_path)

    #Setup llm Ollama
    client = Client(host=OLLAMA_URL)

    try:
        # Copiamos las imágenes al folder de salida para que queden persistentes en ./res
        saved_image_paths = []
        for img in image_paths:
            dest = os.path.join(out_folder, os.path.basename(img))
            shutil.copy(img, dest)
            saved_image_paths.append(dest)

        # Llamada OCR (usando las imágenes en memoria/temporal)
        text = ocr_images(image_paths, client)
        # Guardamos el texto en res
        text_file = os.path.join(out_folder, f"{pdf_stem}_extracted.txt")
        with open(text_file, "w", encoding="utf-8") as f:
            # Si ocr_images devolvió dict/string, lo guardamos tal cual
            if isinstance(text, (dict, list)):
                f.write(str(text))
            else:
                f.write(text)

        print(f"Procesado. Archivos en: {out_folder}")
        print(f"Texto guardado en: {text_file}")
    except requests.exceptions.RequestException as e:
        print(f"Error en la petición a Ollama ({OLLAMA_URL}): {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error inesperado: {e}", file=sys.stderr)
        sys.exit(3)
    finally:
        # Limpiamos el temp dir
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
