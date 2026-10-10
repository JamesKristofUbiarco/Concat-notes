"""Small opt-in API benchmark. Never saves notes, cards or index records."""
import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.knowledge import extract_claims
from app import models
from app.regeneration import generate_selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow a small paid API validation")
    parser.add_argument("--class-id", help="Read-only full generation of one existing class; never archives its result")
    args = parser.parse_args()
    if not args.live:
        parser.error("Use --live to authorize API calls; otherwise run the unit tests")
    if args.class_id:
        started = time.monotonic()
        with SessionLocal() as db:
            note = db.get(models.RawNote, args.class_id)
            if note is None or note.processed_note is None:
                parser.error("The class must exist and have a processed note")
            state = generate_selection(db, note, ["content", "glossary", "flashcards"], "")
            db.rollback()
        print(json.dumps({"seconds": round(time.monotonic() - started, 2), "metrics": {key: value for key, value in state["metrics"].items() if key != "evidence_cache_key"}, "markdown": state["structured_markdown"]}, ensure_ascii=False, indent=2))
        return
    prior_id = str(uuid4())
    note = SimpleNamespace(id=uuid4(), course_name="Generation benchmark (not saved)", class_title="Aplicar ls -a",
        processed_note=None, transcription="El kernel administra los recursos del sistema. Esto ya se explicó. Hoy usamos ls -a: muestra todos los archivos, incluidos los ocultos. Sin -a, ls no muestra los archivos ocultos. No se está describiendo cómo copiar archivos.")
    history = [SimpleNamespace(id=prior_id, concept="Kernel", statement="El kernel administra los recursos del sistema.")]
    metrics = {}
    started = time.monotonic()
    with SessionLocal() as db:
        claims = extract_claims(note, db, history, metrics=metrics)
        db.rollback()
    repeats = [item for item in claims if item["novelty_relation"] == "REPEATS"]
    applications = [item for item in claims if item["novelty_relation"] in {"NEW", "APPLIES", "EXTENDS", "CLARIFIES"} and "ls" in item["statement"].lower()]
    supported = all(item.get("evidence_text") and " ".join(item["evidence_text"].split()).lower() in " ".join(note.transcription.split()).lower() for item in claims)
    result = {"seconds": round(time.monotonic() - started, 2), "claims": claims,
        "checks": {"recall_known_theory": bool(repeats), "preserve_new_application": bool(applications), "literal_evidence": supported},
        "metrics": {key: value for key, value in metrics.items() if key != "evidence_cache_key"}}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not all(result["checks"].values()):
        raise SystemExit("The benchmark did not meet all quality checks")


if __name__ == "__main__":
    main()
