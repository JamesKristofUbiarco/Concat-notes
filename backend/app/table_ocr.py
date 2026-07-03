import io
import logging
import time
from img2table.document import Image
from img2table.ocr import TesseractOCR

logger = logging.getLogger("table_ocr")

def log_info(msg: str):
    logger.info(msg)
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - [TABLE OCR] {msg}", flush=True)

def log_error(msg: str):
    logger.error(msg)
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - [TABLE OCR ERROR] {msg}", flush=True)

def extract_table_from_image(file_bytes: bytes) -> str:
    try:
        log_info("Iniciando extracción de tabla por OCR local (Tesseract)...")
        # Instanciar el motor OCR Tesseract con soporte para español e inglés
        ocr = TesseractOCR(n_threads=2, lang="spa+eng")
        
        # Cargar la imagen desde bytes
        img = Image(src=io.BytesIO(file_bytes))
        
        # Extraer tablas
        # implicit_rows=True y borderless_tables=True ayudan a detectar layouts complejos
        tables = img.extract_tables(ocr=ocr, implicit_rows=True, borderless_tables=True)
        
        if not tables:
            log_info("No se detectó ninguna estructura de tabla por OCR.")
            return "*(No se detectó ninguna estructura de tabla en la imagen por OCR local)*"
            
        markdown_tables = []
        for idx, table in enumerate(tables):
            df = table.df
            if df is not None and not df.empty:
                # Reemplazar posibles NaNs o valores nulos para evitar texto feo
                df = df.fillna("")
                # Convertir a Markdown usando tabulate (usando to_markdown)
                md = df.to_markdown(index=False)
                markdown_tables.append(md)
                
        if not markdown_tables:
            return "*(No se detectó contenido legible en las tablas)*"
            
        result = "\n\n".join(markdown_tables)
        log_info(f"Extracción exitosa: se encontraron {len(markdown_tables)} tabla(s).")
        return result
    except Exception as e:
        log_error(f"Error procesando OCR de tabla: {e}")
        return f"**[Error al procesar la tabla localmente por OCR: {str(e)}]**"
