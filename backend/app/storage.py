import os
import uuid
import json
import boto3
from botocore.client import Config
from sqlalchemy.orm import Session
from google import genai
from google.genai import types

from app import models, llm_models

RUSTFS_ENDPOINT_INTERNAL = os.getenv("RUSTFS_ENDPOINT_INTERNAL", "http://rustfs:9000")
RUSTFS_ENDPOINT_EXTERNAL = os.getenv("RUSTFS_ENDPOINT_EXTERNAL", "http://localhost:9000")
RUSTFS_ACCESS_KEY = os.getenv("RUSTFS_ACCESS_KEY", "rustfs_admin")
RUSTFS_SECRET_KEY = os.getenv("RUSTFS_SECRET_KEY", "rustfs_password")
RUSTFS_BUCKET_NAME = os.getenv("RUSTFS_BUCKET_NAME", "notes-images")

import logging
import time

logger = logging.getLogger("storage")

def log_info(msg: str):
    logger.info(msg)
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - [STORAGE] {msg}", flush=True)

def log_warning(msg: str):
    logger.warning(msg)
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - [STORAGE ADVERTENCIA] {msg}", flush=True)

def log_error(msg: str):
    logger.error(msg)
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - [STORAGE ERROR] {msg}", flush=True)


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=RUSTFS_ENDPOINT_INTERNAL,
        aws_access_key_id=RUSTFS_ACCESS_KEY,
        aws_secret_access_key=RUSTFS_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1"
    )

def init_storage():
    """Inicializa el bucket en RustFS y le asigna una política de lectura pública."""
    try:
        s3 = get_s3_client()
        # Verificar si el bucket existe
        try:
            s3.head_bucket(Bucket=RUSTFS_BUCKET_NAME)
        except Exception:
            # Crear bucket si no existe
            s3.create_bucket(Bucket=RUSTFS_BUCKET_NAME)
            log_info(f"Bucket '{RUSTFS_BUCKET_NAME}' creado exitosamente en RustFS.")
        
        # Establecer política de lectura pública
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicRead",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{RUSTFS_BUCKET_NAME}/*"]
                }
            ]
        }
        s3.put_bucket_policy(Bucket=RUSTFS_BUCKET_NAME, Policy=json.dumps(policy))
        log_info(f"Política de lectura pública establecida para '{RUSTFS_BUCKET_NAME}' en RustFS.")
    except Exception as e:
        log_error(f"No se pudo inicializar RustFS: {e}")

def upload_file_to_rustfs(filename: str, file_bytes: bytes, content_type: str) -> str:
    s3 = get_s3_client()
    s3.put_object(
        Bucket=RUSTFS_BUCKET_NAME,
        Key=filename,
        Body=file_bytes,
        ContentType=content_type
    )
    return f"{RUSTFS_ENDPOINT_EXTERNAL}/{RUSTFS_BUCKET_NAME}/{filename}"

def download_file_from_rustfs(filename: str) -> bytes:
    s3 = get_s3_client()
    response = s3.get_object(Bucket=RUSTFS_BUCKET_NAME, Key=filename)
    return response["Body"].read()

def delete_file_from_rustfs(filename: str) -> bool:
    try:
        s3 = get_s3_client()
        s3.delete_object(Bucket=RUSTFS_BUCKET_NAME, Key=filename)
        return True
    except Exception as e:
        log_error(f"No se pudo eliminar el archivo '{filename}' de RustFS: {e}")
        return False

def analyze_note_images(db: Session, raw_note: models.RawNote):
    """
    Analiza imágenes pendientes usando el transporte explícito del modelo seleccionado.
    """
    # Filtrar imágenes de esta nota sin descripción (excluyendo las que son tipo tabla/OCR)
    images_to_analyze = [img for img in raw_note.images if not img.descripcion_llm and img.image_type != "table"]
    if not images_to_analyze:
        return

    try:
        resolved = llm_models.resolve_selected_model(db, "image_analysis")
    except llm_models.ModelResolutionError as exc:
        log_warning(f"No hay un modelo de visión ejecutable: {exc} Saltando.")
        return

    api_key = os.getenv(resolved.required_env)
    use_openrouter = resolved.transport == llm_models.OPENROUTER_TRANSPORT
    log_info(
        f"Analizando {len(images_to_analyze)} imagen(es): requested='{resolved.requested_model}', "
        f"effective='{resolved.model_id}', via='{resolved.transport}', fallback={resolved.fallback_used}."
    )
    
    client = None
    if not use_openrouter:
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            log_error(f"Error al inicializar el cliente google-genai: {e}")
            return

    for img in images_to_analyze:
        try:
            # 1. Descargar bytes de RustFS
            file_bytes = download_file_from_rustfs(img.filename)
            
            # Determinar MIME type basado en la extensión del archivo
            ext = os.path.splitext(img.filename)[1].lower()
            mime_type = "image/jpeg"
            if ext == ".png":
                mime_type = "image/png"
            elif ext == ".gif":
                mime_type = "image/gif"
            elif ext == ".webp":
                mime_type = "image/webp"

            prompt = "Describe la imagen e incluye todo el texto que contiene, después devuelve el resultado en formato md envuelto por backticks"
            
            if use_openrouter:
                import base64
                import requests
                
                base64_image = base64.b64encode(file_bytes).decode("utf-8")
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/JamesKristofUbiarco/Concat-notes",
                    "X-Title": "Gestor Inteligente de Notas"
                }
                
                payload = {
                    "model": resolved.api_model_id,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ]
                }
                
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120
                )
                response.raise_for_status()
                res_data = response.json()
                desc = res_data["choices"][0]["message"]["content"].strip()
            else:
                # Invocar Gemini 3.6 Flash nativo
                response = client.models.generate_content(
                    model=resolved.api_model_id,
                    contents=[
                        types.Part.from_bytes(
                            data=file_bytes,
                            mime_type=mime_type
                        ),
                        prompt
                    ]
                )
                desc = response.text.strip() if response.text else ""
            
            # Limpiar posibles bloques markdown envolventes si el modelo los retorna literalmente
            if desc.startswith("```markdown"):
                desc = desc[11:].strip()
            elif desc.startswith("```"):
                desc = desc[3:].strip()
            if desc.endswith("```"):
                desc = desc[:-3].strip()

            # 3. Guardar en base de datos
            img.descripcion_llm = desc
            db.add(img)
            db.commit()
            log_info(f"Imagen '{img.filename}' analizada y guardada exitosamente. Descripción del LLM: {desc[:150]}...")
            
        except Exception as e:
            log_error(f"Error al analizar imagen '{img.filename}': {e}")
