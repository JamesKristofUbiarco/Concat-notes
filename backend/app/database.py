import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Cargar variables de entorno del archivo .env o del sistema
load_dotenv()

# Obtener URL de conexión de la base de datos (por defecto para desarrollo local en Docker)
raw_db_url = os.getenv(
    "DATABASE_URL", 
    "postgresql://notes_user:notes_password@localhost:5432/notes_db"
)
# psycopg 3 requiere el prefijo postgresql+psycopg:// en SQLAlchemy
if raw_db_url.startswith("postgresql://"):
    DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    DATABASE_URL = raw_db_url

# Configurar el motor de base de datos SQLAlchemy
# pool_pre_ping=True ayuda a recuperar conexiones caídas automáticamente
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True
)

# Factoría de sesiones de base de datos
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)

# Clase base declarativa para heredar modelos de tablas de base de datos
Base = declarative_base()

# Dependencia para inyectar sesiones de base de datos en las rutas HTTP de FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
