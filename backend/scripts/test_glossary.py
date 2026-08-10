import sys
import os

# Añadir el path para importar app
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.glossary import parse_glossary_entries, merge_entries, compile_glossary_markdown

def run_tests():
    print("=== Iniciando pruebas unitarias de Glosario ===")
    
    # 1. Test parse_glossary_entries
    sample_markdown = """
# Clase 5: Sincronización de Procesos

## 📝 Apuntes de Clase
Aquí van apuntes generales...

## 📖 Conceptos Clave (Glosario)

**Semaphore** #definicion
Un semaphore (semáforo) es un mecanismo de sincronización que controla el acceso a recursos compartidos
mediante un contador entero. Operaciones: `wait()` y `signal()`.

**Semaphore** #definicion-ampliada
Los semáforos binarios (valores 0 y 1) son funcionalmente equivalentes
a los mutex, aunque el mutex tiene noción de "dueño".

**Semaphore** #enciclopedia
Propuesto por Edsger Dijkstra en 1965. Las operaciones P (proberen) y
V (verhogen) provienen del holandés.

**Deadlock** #definicion
Un deadlock (interbloqueo) es una situación donde dos o más procesos quedan bloqueados indefinidamente,
cada uno esperando un recurso que otro posee.

## 🗃️ Flashcards
#flashcards/SO/Sincronizacion
...
"""
    
    print("1. Probando parse_glossary_entries...")
    entries = parse_glossary_entries(sample_markdown, "Clase 5: Sincronización")
    
    assert len(entries) == 4, f"Se esperaban 4 entradas, se obtuvieron {len(entries)}"
    
    # Verificar semáforo definición
    semaforo_def = next(e for e in entries if e["term"] == "Semaphore" and e["type"] == "definicion")
    assert semaforo_def["term_es"] == "semáforo", "Traducción española incorrecta"
    assert "semaphore (semáforo)" in semaforo_def["content"], "Traducción o contenido incorrectos"
    
    # Verificar semáforo ampliado
    semaforo_amp = next(e for e in entries if e["term"] == "Semaphore" and e["type"] == "definicion-ampliada")
    content_clean = semaforo_amp["content"].replace('\n', ' ')
    assert "equivalentes a los mutex" in content_clean, "Contenido incorrecto"
    
    # Verificar deadlock definición
    deadlock_def = next(e for e in entries if e["term"] == "Deadlock" and e["type"] == "definicion")
    assert "deadlock (interbloqueo)" in deadlock_def["content"]
    
    print("   ✓ parse_glossary_entries pasó exitosamente!")
    
    # 2. Test merge_entries
    print("2. Probando merge_entries...")
    existing_entries = [
        {
            "term": "Semaphore",
            "term_es": "semáforo",
            "definition": "Mecanismo antiguo de control de acceso.",
            "expansions": ["Anteriormente explicado."],
            "encyclopedia": [],
            "sources": ["Clase 4: Exclusión Mutua"]
        }
    ]
    
    merged = merge_entries(existing_entries, entries)
    
    # Debe haber 2 términos en total: Semáforo y Deadlock
    assert len(merged) == 2, f"Se esperaban 2 términos fusionados, se obtuvieron {len(merged)}"
    
    semaforo_merged = next(e for e in merged if e["term"] == "Semaphore")
    assert semaforo_merged["definition"] == "Mecanismo antiguo de control de acceso.", "La definición existente no debió sobrescribirse"
    def get_content(x):
        return x if isinstance(x, str) else x["content"]
        
    assert len(semaforo_merged["expansions"]) == 3, f"Se esperaban 3 expansiones, se obtuvieron {len(semaforo_merged['expansions'])}"
    # La nueva definición principal de la Clase 5 debe haber pasado a expansions
    assert any("mecanismo de sincronización que controla el acceso" in get_content(exp).replace('\n', ' ') for exp in semaforo_merged["expansions"]), "La nueva definición no se guardó en expansiones"
    assert any("equivalentes a los mutex" in get_content(exp).replace('\n', ' ') for exp in semaforo_merged["expansions"]), "La ampliación no se guardó en expansiones"
    assert len(semaforo_merged["encyclopedia"]) == 1, "Se esperaba 1 entrada de enciclopedia"
    assert "Dijkstra" in get_content(semaforo_merged["encyclopedia"][0])
    assert "Clase 4: Exclusión Mutua" in semaforo_merged["sources"]
    assert "Clase 5: Sincronización" in semaforo_merged["sources"]
    
    print("   ✓ merge_entries pasó exitosamente!")
    
    # 3. Test compile_glossary_markdown
    print("3. Probando compile_glossary_markdown...")
    compiled_md = compile_glossary_markdown(merged, "Sistemas Operativos")
    
    assert "tipo: glosario" in compiled_md
    assert "curso: Sistemas Operativos" in compiled_md
    assert "## S" in compiled_md
    assert "### Semaphore" in compiled_md
    assert "### Semaphore (" not in compiled_md
    assert "## D" in compiled_md
    assert "### Deadlock" in compiled_md
    assert "[[Clase 4: Exclusión Mutua]]" in compiled_md
    assert "[[Clase 5: Sincronización]]" in compiled_md
    
    # Verificar orden alfabético: D debe estar antes de S
    d_pos = compiled_md.find("## D")
    s_pos = compiled_md.find("## S")
    assert d_pos < s_pos, "El orden alfabético es incorrecto (S antes de D)"
    
    print("   ✓ compile_glossary_markdown pasó exitosamente!")
    print("=== ¡TODAS LAS PRUEBAS PASARON EXITOSAMENTE! ===")

if __name__ == "__main__":
    run_tests()
