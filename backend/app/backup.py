import os
import io
import zipfile
import tempfile
import subprocess
import logging
import mimetypes
from pathlib import PurePosixPath
from app.storage import get_s3_client, RUSTFS_BUCKET_NAME, init_storage

logger = logging.getLogger("backup")

def get_clean_db_url() -> str:
    """
    Obtiene la URL de la base de datos limpia de prefijos de SQLAlchemy
    para que sea compatible con pg_dump y pg_restore.
    """
    raw_db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://notes_user:notes_password@db:5432/notes_db"
    )
    # Reemplazar el driver de sqlalchemy para que pg_dump lo entienda
    return raw_db_url.replace("postgresql+psycopg://", "postgresql://")

def create_full_backup() -> io.BytesIO:
    """
    Genera un archivo ZIP en memoria conteniendo:
    1. Un dump de PostgreSQL (database.dump)
    2. Las imágenes almacenadas en RustFS (directorio images/)
    """
    logger.info("Iniciando generación de respaldo completo...")
    
    zip_buffer = io.BytesIO()
    db_url = get_clean_db_url()
    
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as temp_dump:
        temp_dump_name = temp_dump.name

    try:
        # 1. Ejecutar pg_dump por TCP contra el host de la base de datos
        logger.info("Ejecutando pg_dump...")
        cmd = [
            "pg_dump",
            "-F", "c",          # Formato custom (binario comprimido de postgres)
            "-b",               # Incluir blobs
            "-v",               # Modo verbose
            "-f", temp_dump_name,
            db_url
        ]
        
        # Ejecutar subprocess
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"pg_dump completado con éxito: {result.stdout}")
        
        # Leer el contenido del dump generado
        with open(temp_dump_name, "rb") as f:
            dump_data = f.read()

        # 2. Empaquetar todo en el archivo ZIP
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Añadir dump de base de datos
            zip_file.writestr("database.dump", dump_data)
            logger.info("Base de datos añadida al ZIP (database.dump).")
            
            # Añadir imágenes de RustFS
            logger.info("Listando y descargando imágenes de RustFS...")
            s3 = get_s3_client()
            
            # Inicializar bucket por si acaso no existiera
            init_storage()
            
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=RUSTFS_BUCKET_NAME):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    logger.info(f"Descargando imagen para backup: {key}")
                    try:
                        res = s3.get_object(Bucket=RUSTFS_BUCKET_NAME, Key=key)
                        img_bytes = res["Body"].read()
                        zip_file.writestr(f"images/{key}", img_bytes)
                    except Exception as e:
                        logger.error(f"Error al respaldar la imagen {key}: {e}")

        zip_buffer.seek(0)
        logger.info("Respaldo completo generado exitosamente.")
        return zip_buffer

    finally:
        # Limpiar archivo temporal en el host del backend
        if os.path.exists(temp_dump_name):
            os.remove(temp_dump_name)

def restore_full_backup(zip_bytes: bytes) -> dict:
    """
    Restaura el sistema completo a partir de un archivo ZIP:
    1. Ejecuta pg_restore para la base de datos (eliminando tablas actuales).
    2. Sube todas las imágenes al bucket de RustFS (limpiando las previas).
    """
    logger.info("Iniciando restauración de respaldo completo...")
    db_url = get_clean_db_url()
    
    zip_buffer = io.BytesIO(zip_bytes)
    images_restored = 0
    
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as temp_dump:
        temp_dump_name = temp_dump.name

    try:
        # 1. Descomprimir y procesar el archivo ZIP
        with zipfile.ZipFile(zip_buffer, "r") as zip_file:
            max_uncompressed = int(os.getenv("MAX_BACKUP_UNCOMPRESSED_MB", "4096")) * 1024 * 1024
            total_uncompressed = sum(info.file_size for info in zip_file.infolist())
            if total_uncompressed > max_uncompressed:
                raise ValueError("El contenido descomprimido del respaldo supera el límite configurado.")

            # Validar existencia del dump
            if "database.dump" not in zip_file.namelist():
                raise ValueError("El archivo ZIP no contiene un respaldo válido de base de datos (database.dump).")

            image_entries = []
            for info in zip_file.infolist():
                if not info.filename.startswith("images/") or info.is_dir():
                    continue
                key = info.filename.removeprefix("images/")
                key_path = PurePosixPath(key)
                if not key or key_path.is_absolute() or ".." in key_path.parts:
                    raise ValueError(f"Ruta de imagen inválida en el respaldo: {info.filename}")
                image_entries.append((info, key))
            
            # Extraer dump de la base de datos
            dump_data = zip_file.read("database.dump")
            with open(temp_dump_name, "wb") as f:
                f.write(dump_data)
            
            # 2. Ejecutar pg_restore contra la base de datos
            logger.info("Ejecutando pg_restore...")
            cmd = [
                "pg_restore",
                "--clean",      # Limpiar objetos antes de recrear
                "--if-exists",
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",   # Omitir comandos de asignación de propietario
                "-d", db_url,
                temp_dump_name
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            logger.info(f"pg_restore stdout: {result.stdout}")
            if result.returncode != 0:
                logger.error(f"pg_restore falló con código {result.returncode}. stderr: {result.stderr}")
                raise subprocess.CalledProcessError(
                    result.returncode, 
                    cmd, 
                    output=result.stdout, 
                    stderr=result.stderr
                )
            logger.info("pg_restore completado de forma atómica.")
            
            # 3. Limpiar y restaurar imágenes en RustFS
            logger.info("Limpiando y restaurando imágenes en RustFS...")
            s3 = get_s3_client()
            
            # Inicializar y crear bucket si no existe
            init_storage()
            
            # Eliminar objetos actuales del bucket
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=RUSTFS_BUCKET_NAME):
                for obj in page.get("Contents", []):
                    logger.info(f"Eliminando imagen existente para sobreescribir: {obj['Key']}")
                    s3.delete_object(Bucket=RUSTFS_BUCKET_NAME, Key=obj["Key"])
                
            # Extraer y subir las imágenes previamente validadas del ZIP.
            for info, key in image_entries:
                img_bytes = zip_file.read(info)
                content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"

                logger.info(f"Subiendo imagen restaurada a RustFS: {key}")
                s3.put_object(
                    Bucket=RUSTFS_BUCKET_NAME,
                    Key=key,
                    Body=img_bytes,
                    ContentType=content_type,
                )
                images_restored += 1

        logger.info(f"Restauración finalizada. Imágenes restauradas: {images_restored}")
        return {
            "status": "success",
            "message": "La base de datos y el almacenamiento de objetos fueron restaurados con éxito.",
            "images_restored": images_restored
        }

    finally:
        # Limpiar archivo temporal en el host del backend
        if os.path.exists(temp_dump_name):
            os.remove(temp_dump_name)
