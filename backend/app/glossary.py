import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app import models, crud
from langchain_core.runnables import RunnableConfig

def parse_glossary_entries(markdown: str, note_title: str) -> List[Dict[str, Any]]:
    """
    Parseza la sección '## 📖 Conceptos Clave (Glosario)' de una nota markdown
    y extrae las definiciones, definiciones ampliadas y entradas de enciclopedia.
    """
    entries = []
    
    # Encontrar la sección de glosario.
    # Buscamos desde "## 📖 Conceptos Clave" hasta el siguiente heading de nivel 2 (##) o el final del archivo.
    match = re.search(r'## 📖 Conceptos Clave \(Glosario\)(.*?)(?=\n## |\Z)', markdown, re.DOTALL | re.IGNORECASE)
    if not match:
        return entries
        
    section_text = match.group(1)
    
    # Analizar línea a línea para extraer los conceptos y sus bloques de texto
    lines = section_text.split('\n')
    
    current_entry = None
    current_content = []
    
    # Regex para detectar una cabecera de concepto: **Concepto (Concepto EN)** #etiqueta
    # Admite también si no tiene el término en inglés o si hay espacios extra.
    header_pattern = re.compile(r'^\s*\*\*(.*?)\*\*\s+(#(?:definicion-ampliada|definicion|enciclopedia|formula|usos))\b', re.IGNORECASE)
    
    def save_current():
        nonlocal current_entry, current_content
        if current_entry and current_content:
            content_text = '\n'.join(current_content).strip()
            if content_text:
                current_entry['content'] = content_text
                entries.append(current_entry)
        current_content = []
        current_entry = None

    for line in lines:
        header_match = header_pattern.match(line)
        if header_match:
            # Primero guardamos la entrada que estábamos acumulando
            save_current()
            
            raw_term = header_match.group(1).strip()
            tag = header_match.group(2).lower()
            
            # Limpiar etiqueta
            entry_type = tag.replace('#', '')
            
            # Extraer término en inglés si existe en formato "Término (Term EN)"
            term = raw_term
            term_en = None
            en_match = re.search(r'\(([^)]+)\)$', raw_term)
            if en_match:
                term_en = en_match.group(1).strip()
                term = re.sub(r'\s*\([^)]+\)$', '', raw_term).strip()
                
            current_entry = {
                "term": term,
                "term_en": term_en,
                "type": entry_type,
                "source": note_title,
                "content": ""
            }
        elif current_entry is not None:
            # Si empieza con otra sección ## o ###, o es una línea divisoria, guardamos y cerramos
            if line.strip().startswith('##') or re.match(r'^\s*---\s*$', line):
                save_current()
            else:
                current_content.append(line)
                
    # Guardar el último
    save_current()
    
    return entries


def normalize_term(term: str) -> str:
    """
    Normaliza un término para facilitar la comparación y agrupamiento de sinónimos
    y variaciones (ej. 'Distribución' vs 'Distribución de Linux', pluriles vs singulares).
    """
    term = term.lower().strip()
    # Eliminar acentos
    term = re.sub(r'[áàäâ]', 'a', term)
    term = re.sub(r'[éèëê]', 'e', term)
    term = re.sub(r'[íìïî]', 'i', term)
    term = re.sub(r'[óòöô]', 'o', term)
    term = re.sub(r'[úùüû]', 'u', term)
    # Eliminar artículos, preposiciones y palabras de relleno comunes
    term = re.sub(r'\b(de linux|de|del|el|la|los|las|un|una|unos|unas|para|en)\b', '', term)
    # Eliminar la 's' final en cada palabra para normalizar singulares y plurales
    term = ' '.join(re.sub(r's\b', '', word) for word in term.split())
    # Eliminar caracteres no alfanuméricos y espacios extra
    term = re.sub(r'[^a-z0-9]', '', term)
    return term.strip()


def merge_entries(existing_entries: List[Dict[str, Any]], new_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fusiona de forma inteligente las nuevas entradas extraídas con las preexistentes en el glosario del curso.
    """
    # Indexar entradas existentes por término normalizado y term_key
    entries_map: Dict[str, Dict[str, Any]] = {}
    normalized_map: Dict[str, str] = {} # term_normalizado -> term_key
    
    for entry in existing_entries:
        term_key = entry["term"].strip().lower()
        
        # Asegurarnos de que tenga las llaves nuevas inicializadas
        if "definition_sources" not in entry:
            entry["definition_sources"] = list(entry.get("sources", [])) if "sources" in entry else []
            
        entry.setdefault("expansions", [])
        entry.setdefault("encyclopedia", [])
        entry.setdefault("formulas", [])
        entry.setdefault("uses", [])
        
        entries_map[term_key] = entry
        norm = normalize_term(entry["term"])
        if norm:
            normalized_map[norm] = term_key

    for new_entry in new_entries:
        term = new_entry["term"].strip()
        term_key = term.lower()
        entry_type = new_entry["type"]
        content = new_entry["content"].strip()
        source = new_entry["source"].strip()
        
        # Buscar coincidencia por término normalizado
        norm_new = normalize_term(term)
        matched_key = term_key
        
        if norm_new in normalized_map:
            # Encontró un concepto existente equivalente
            matched_key = normalized_map[norm_new]
        elif term_key in entries_map:
            matched_key = term_key
        else:
            # Si no existe, creamos la estructura base
            matched_key = term_key
            entries_map[matched_key] = {
                "term": term,
                "term_en": new_entry.get("term_en"),
                "definition": "",
                "definition_sources": [],
                "expansions": [],
                "encyclopedia": [],
                "formulas": [],
                "uses": [],
                "sources": []
            }
            if norm_new:
                normalized_map[norm_new] = matched_key
            
        entry_data = entries_map[matched_key]
        
        # Sincronizar fuentes (evitar duplicados globales)
        if source and source not in entry_data.setdefault("sources", []):
            entry_data["sources"].append(source)
            
        # Actualizar term_en si no estaba y ahora viene
        if new_entry.get("term_en") and not entry_data.get("term_en"):
            entry_data["term_en"] = new_entry["term_en"]
            
        # Función auxiliar para fusionar elementos en colecciones estructuradas
        def merge_into_collection(collection_key: str, item_content: str, item_source: str):
            collection = entry_data.setdefault(collection_key, [])
            found = False
            for i, exp in enumerate(collection):
                # exp puede ser str (de datos antiguos) o dict/GlossaryItem
                exp_content = exp if isinstance(exp, str) else exp.get("content", "")
                if exp_content == item_content:
                    found = True
                    # Si ya existe y es dict, agregamos el source
                    if isinstance(exp, dict):
                        if item_source and item_source not in exp.setdefault("sources", []):
                            exp["sources"].append(item_source)
                    # Si es str, lo convertimos a dict para poder registrar la fuente
                    elif isinstance(exp, str):
                        collection[i] = {
                            "content": exp,
                            "sources": [item_source] if item_source else []
                        }
                    break
            
            # Si no existe, lo agregamos como dict
            if not found:
                collection.append({
                    "content": item_content,
                    "sources": [item_source] if item_source else []
                })

        # Fusionar contenido según el tipo
        if entry_type == "definicion":
            # Si no hay definición principal, asignarla.
            if not entry_data["definition"]:
                entry_data["definition"] = content
                entry_data["definition_sources"] = [source] if source else []
            else:
                # Si la definición ya existe pero es idéntica, solo agregamos la fuente
                if entry_data["definition"] == content:
                    if source and source not in entry_data.setdefault("definition_sources", []):
                        entry_data["definition_sources"].append(source)
                else:
                    # Si es una definición diferente, la pasamos a "expansions"
                    merge_into_collection("expansions", content, source)

        elif entry_type == "definicion-ampliada":
            # Evitamos duplicar la definición principal
            if content != entry_data["definition"]:
                merge_into_collection("expansions", content, source)
            else:
                if source and source not in entry_data.setdefault("definition_sources", []):
                    entry_data["definition_sources"].append(source)

        elif entry_type == "enciclopedia":
            merge_into_collection("encyclopedia", content, source)
        elif entry_type == "formula":
            merge_into_collection("formulas", content, source)
        elif entry_type == "usos":
            merge_into_collection("uses", content, source)
                
    # Retornar como lista ordenada alfabéticamente por el nombre del término
    merged_list = list(entries_map.values())
    merged_list.sort(key=lambda x: x["term"].lower())
    return merged_list


def compile_glossary_markdown(entries: List[Dict[str, Any]], course_name: str) -> str:
    """
    Genera el documento Markdown final ordenado alfabéticamente a partir de las entradas estructuradas.
    """
    if not entries:
        return ""
        
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    md_lines = [
        "---",
        "tipo: glosario",
        f"curso: {course_name}",
        "estado: auto_generado",
        f"ultima_actualizacion: {date_str}",
        "---",
        f"# 📖 Glosario — {course_name}\n"
    ]
    
    # Agrupar entradas por letra inicial
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        first_letter = entry["term"][0].upper() if entry["term"] else "#"
        if not first_letter.isalpha():
            first_letter = "#"
        if first_letter not in grouped:
            grouped[first_letter] = []
        grouped[first_letter].append(entry)
        
    # Ordenar grupos por letra
    sorted_letters = sorted(grouped.keys())
    
    for letter in sorted_letters:
        md_lines.append(f"## {letter}\n")
        
        # Ordenar términos dentro del grupo
        group_entries = grouped[letter]
        group_entries.sort(key=lambda x: x["term"].lower())
        
        for entry in group_entries:
            term_header = entry["term"]
            if entry.get("term_en"):
                term_header += f" ({entry['term_en']})"
                
            md_lines.append(f"### {term_header}")
            
            # Helper para formatear fuentes
            def format_sources(sources_list):
                if not sources_list:
                    return ""
                return "\nFuente: " + ", ".join(f"[[{src}]]" for src in sources_list)
            
            # Definición principal
            if entry["definition"]:
                sources_str = format_sources(entry.get("definition_sources", []))
                md_lines.append(f"#definicion {entry['definition']}{sources_str}\n")
            elif entry["expansions"]:
                # Si no tiene definición principal pero sí expansiones, usar la primera como tal
                first_exp = entry["expansions"][0]
                exp_content = first_exp if isinstance(first_exp, str) else first_exp.get("content", "")
                exp_sources = [] if isinstance(first_exp, str) else first_exp.get("sources", [])
                sources_str = format_sources(exp_sources)
                md_lines.append(f"#definicion {exp_content}{sources_str}\n")
                
            # Definiciones ampliadas (saltamos la primera si se usó como fallback de definición)
            start_idx = 0 if entry["definition"] else 1
            for exp in entry["expansions"][start_idx:]:
                exp_content = exp if isinstance(exp, str) else exp.get("content", "")
                exp_sources = [] if isinstance(exp, str) else exp.get("sources", [])
                sources_str = format_sources(exp_sources)
                md_lines.append(f"#definicion-ampliada {exp_content}{sources_str}\n")
                
            # Enciclopedia
            for enc in entry.get("encyclopedia", []):
                enc_content = enc if isinstance(enc, str) else enc.get("content", "")
                enc_sources = [] if isinstance(enc, str) else enc.get("sources", [])
                sources_str = format_sources(enc_sources)
                md_lines.append(f"> #enciclopedia {enc_content}{sources_str}\n")
                
            # Fórmulas
            for formula in entry.get("formulas", []):
                form_content = formula if isinstance(formula, str) else formula.get("content", "")
                form_sources = [] if isinstance(formula, str) else formula.get("sources", [])
                sources_str = format_sources(form_sources)
                md_lines.append(f"#formula {form_content}{sources_str}\n")
                
            # Usos
            for use in entry.get("uses", []):
                use_content = use if isinstance(use, str) else use.get("content", "")
                use_sources = [] if isinstance(use, str) else use.get("sources", [])
                sources_str = format_sources(use_sources)
                md_lines.append(f"**Ejemplo de uso práctico:**\n#usos {use_content}{sources_str}\n")
                
            md_lines.append("---")
            
        # Remover el último separador del grupo
        if md_lines[-1] == "---":
            md_lines.pop()
            
    return '\n'.join(md_lines)


def glossary_extraction_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    Nodo de LangGraph que extrae conceptos clave de la nota generada, los fusiona
    con el glosario actual y guarda la versión compilada en la base de datos.
    """
    db: Session = config["configurable"]["db"]
    raw_note_id = state["raw_note_id"]
    structured_markdown = state.get("structured_markdown", "")
    
    # Obtener metadatos de la nota cruda para conocer el curso y el título de la clase
    note = db.query(models.RawNote).filter(models.RawNote.id == raw_note_id).first()
    if not note or not structured_markdown:
        return state
        
    course_name = note.course_name
    note_title = note.class_title
    
    # 1. Parsear nuevas definiciones de la nota Markdown
    new_entries = parse_glossary_entries(structured_markdown, note_title)
    if not new_entries:
        return state
        
    # 2. Cargar glosario existente
    glossary = crud.get_course_glossary(db, course_name)
    existing_entries = glossary.entries if glossary else []
    
    # 3. Mezclar entradas antiguas y nuevas
    merged = merge_entries(existing_entries, new_entries)
    
    # 4. Generar Markdown compilado
    compiled_md = compile_glossary_markdown(merged, course_name)
    
    # 5. Guardar en la DB
    crud.save_course_glossary(db, course_name, merged, compiled_md)
    
    return state
