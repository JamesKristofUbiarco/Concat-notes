import os
import sys

# Configurar path para importar app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import CourseGlossary
from app.glossary import merge_entries, compile_glossary_markdown

def clean_all_glossaries():
    db = SessionLocal()
    try:
        glossaries = db.query(CourseGlossary).all()
        print(f"Encontrados {len(glossaries)} glosarios en la base de datos para limpiar...")
        
        for glossary in glossaries:
            old_entries = glossary.entries or []
            if not old_entries:
                continue
                
            # Convertir entradas a formato plano que merge_entries espera como entrada
            flat_entries = []
            for entry in old_entries:
                term = entry.get("term", "")
                term_es = entry.get("term_es")
                if not term_es and entry.get("term_en"):
                    term_es = term
                    term = entry["term_en"]
                sources = entry.get("sources", [])
                source = sources[0] if sources else "Migración"
                
                # 1. Definición principal
                if entry.get("definition"):
                    flat_entries.append({
                        "term": term,
                        "term_es": term_es,
                        "type": "definicion",
                        "content": entry["definition"],
                        "source": source
                    })
                    
                # 2. Expansiones
                for exp in entry.get("expansions", []):
                    flat_entries.append({
                        "term": term,
                        "term_es": term_es,
                        "type": "definicion-ampliada",
                        "content": exp,
                        "source": source
                    })
                    
                # 3. Enciclopedia
                for enc in entry.get("encyclopedia", []):
                    flat_entries.append({
                        "term": term,
                        "term_es": term_es,
                        "type": "enciclopedia",
                        "content": enc,
                        "source": source
                    })
                    
                # 4. Fórmulas
                for formula in entry.get("formulas", []):
                    flat_entries.append({
                        "term": term,
                        "term_es": term_es,
                        "type": "formula",
                        "content": formula,
                        "source": source
                    })
                    
                # 5. Usos
                for use in entry.get("uses", []):
                    flat_entries.append({
                        "term": term,
                        "term_es": term_es,
                        "type": "usos",
                        "content": use,
                        "source": source
                    })
            
            # Realizar fusión limpia usando la nueva lógica
            cleaned_entries = merge_entries([], flat_entries)
            
            # Sincronizar fuentes agregando todas las originales
            for old_ent in old_entries:
                old_term_norm = old_ent.get("term", "").strip().lower()
                for cleaned_ent in cleaned_entries:
                    if cleaned_ent["term"].strip().lower() == old_term_norm:
                        for src in old_ent.get("sources", []):
                            if src not in cleaned_ent["sources"]:
                                cleaned_ent["sources"].append(src)
            
            # Actualizar en la base de datos
            glossary.entries = cleaned_entries
            glossary.compiled_markdown = compile_glossary_markdown(cleaned_entries, glossary.course_name)
            print(f" - Glosario del curso '{glossary.course_name}' limpiado con éxito. Reducido de {len(old_entries)} a {len(cleaned_entries)} conceptos.")
            
        db.commit()
        print("Limpieza completada de manera exitosa en toda la base de datos.")
    except Exception as e:
        db.rollback()
        print(f"Error al limpiar glosarios: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clean_all_glossaries()
