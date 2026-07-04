import io
import logging
import time
import pandas as pd
from img2table.document import Image
from img2table.ocr import TesseractOCR

logger = logging.getLogger("table_ocr")

def log_info(msg: str):
    logger.info(msg)
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - [TABLE OCR] {msg}", flush=True)

def log_error(msg: str):
    logger.error(msg)
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - [TABLE OCR ERROR] {msg}", flush=True)

def merge_split_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.shape[0] <= 1:
        return df
        
    merged_rows = []
    current_row = None
    
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        if current_row is None:
            current_row = row_dict
            continue
            
        # Determinar si la fila actual es una continuación de la anterior
        is_continuation = False
        
        # Condición A: La primera columna está vacía
        first_col_val = str(row_dict.get(df.columns[0], "")).strip()
        if not first_col_val:
            is_continuation = True
        # Condición B: La primera columna tiene texto, pero todas las demás están vacías
        elif all(not str(row_dict.get(col, "")).strip() for col in list(df.columns)[1:]):
            is_continuation = True
        # Condición C: La segunda columna (Col 1) está vacía
        elif len(df.columns) > 1 and not str(row_dict.get(df.columns[1], "")).strip():
            is_continuation = True
            
        if is_continuation:
            # Fusionar texto en cada celda
            for col in df.columns:
                val_curr = str(row_dict.get(col, "")).strip()
                val_prev = str(current_row.get(col, "")).strip()
                if val_curr:
                    if val_prev:
                        current_row[col] = f"{val_prev} {val_curr}"
                    else:
                        current_row[col] = val_curr
        else:
            merged_rows.append(current_row)
            current_row = row_dict
            
    if current_row is not None:
        merged_rows.append(current_row)
        
    return pd.DataFrame(merged_rows)

def extract_table_from_image(file_bytes: bytes) -> str:
    try:
        log_info("Iniciando extracción de tabla por OCR local (Tesseract)...")
        # Instanciar el motor OCR Tesseract con soporte para español e inglés
        ocr = TesseractOCR(n_threads=2, lang="spa+eng")
        
        # Cargar la imagen desde bytes
        img = Image(src=io.BytesIO(file_bytes))
        
        # Extraer tablas
        # implicit_rows=False evita interpretar renglones múltiples en celdas como filas separadas
        tables = img.extract_tables(ocr=ocr, implicit_rows=False, borderless_tables=True)
        
        if not tables:
            log_info("No se detectó ninguna estructura de tabla por OCR.")
            return "*(No se detectó ninguna estructura de tabla en la imagen por OCR local)*"
            
        markdown_tables = []
        for idx, table in enumerate(tables):
            df = table.df
            if df is not None and not df.empty:
                # 1. Promocionar la primera fila como cabecera si las columnas actuales son numéricas por defecto
                is_numeric_cols = all(str(col).isdigit() for col in df.columns) or list(df.columns) == list(range(df.shape[1]))
                if is_numeric_cols and df.shape[0] > 0:
                    new_header = [str(x).strip() if (x is not None and x == x) else "" for x in df.iloc[0].tolist()]
                    if any(h for h in new_header):
                        df.columns = new_header
                        df = df.iloc[1:]
                
                # 2. Limpiar posibles NaNs y valores nulos
                df = df.fillna("")
                
                # 3. Colapsar saltos de línea y múltiples espacios de cada celda en un espacio simple
                map_func = getattr(df, "map", getattr(df, "applymap", None))
                if map_func:
                    df = map_func(lambda x: " ".join(str(x).split()) if x is not None else "")
                else:
                    for col in df.columns:
                        df[col] = df[col].apply(lambda x: " ".join(str(x).split()) if x is not None else "")
                
                # 4. Fusionar filas que son continuaciones de celdas divididas verticalmente
                df = merge_split_rows(df)
                
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
