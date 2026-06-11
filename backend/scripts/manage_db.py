#!/usr/bin/env python
"""
Database Management Script for Notes Concatenator
Supports:
  1. backup: Back up PostgreSQL database to a local dump file.
  2. restore: Restore PostgreSQL database from a local dump file.
  3. import: Idempotently parse and import markdown notes from a folder.
"""

import os
import sys
import re
import argparse
import subprocess
from datetime import datetime

# Set up python path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app import models, crud
from app.database import SessionLocal
from app.worker import _store_embedding

# Docker container database settings
CONTAINER_NAME = "proyecto_notas_db"
DB_USER = "notes_user"
DB_NAME = "notes_db"

def run_cmd(cmd):
    """Executes a shell command and returns output. Raises exception if command fails."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Command failed (code {result.returncode}): {cmd}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
    return result.stdout

def cmd_backup(args):
    """Backs up database from Docker container to a local file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    
    file_path = args.file or os.path.join(backup_dir, f"backup_{timestamp}.dump")
    print(f"Starting backup of database to {file_path}...")
    
    try:
        # Step 1: Run pg_dump inside container to a temp file
        run_cmd(f"docker exec {CONTAINER_NAME} pg_dump -U {DB_USER} -d {DB_NAME} -F c -b -v -f /tmp/db_backup.dump")
        # Step 2: Copy dump file from container to host
        run_cmd(f"docker cp {CONTAINER_NAME}:/tmp/db_backup.dump \"{file_path}\"")
        # Step 3: Clean up temp file in container
        run_cmd(f"docker exec {CONTAINER_NAME} rm /tmp/db_backup.dump")
        
        print(f"Backup completed successfully! Saved to: {file_path}")
    except Exception as e:
        print(f"ERROR: Backup failed: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_restore(args):
    """Restores database in Docker container from a local dump file."""
    file_path = args.file
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Restoring database from {file_path}...")
    try:
        # Step 1: Copy file to container
        run_cmd(f"docker cp \"{file_path}\" {CONTAINER_NAME}:/tmp/db_restore.dump")
        # Step 2: Run pg_restore in container
        # --clean drops database objects before recreating them
        # --no-owner skips restoration of object ownership
        run_cmd(f"docker exec {CONTAINER_NAME} pg_restore -U {DB_USER} -d {DB_NAME} --clean --no-owner /tmp/db_restore.dump")
        # Step 3: Clean up temp file in container
        run_cmd(f"docker exec {CONTAINER_NAME} rm /tmp/db_restore.dump")
        
        print("Restore completed successfully!")
    except Exception as e:
        print(f"ERROR: Restore failed: {e}", file=sys.stderr)
        sys.exit(1)

# --- Note Parsing & Importing Functions ---

def parse_yaml_frontmatter(yaml_text):
    """Simple parser for YAML frontmatter without external dependencies."""
    data = {}
    if not yaml_text:
        return data
    for line in yaml_text.strip().split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            data[key.strip()] = val.strip()
    return data

def parse_date(date_str):
    """Parses date string into a datetime object."""
    if not date_str:
        return datetime.utcnow()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.utcnow()

def normalize_course_name(course_name):
    name = course_name.strip()
    if "aprende react" in name.lower():
        return "Aprende React desde cero"
    if "master completo en python" in name.lower() or "master completo de python" in name.lower():
        return "Master Completo en Python de Cero a Experto"
    if "sql de cero" in name.lower() or "postgresql" in name.lower():
        return "SQL de cero: Tu guía práctica con PostgreSQL"
    if "claude code" in name.lower():
        return "Curso de Claude Code"
    if "fundamentos de bases de datos" in name.lower() or "bases de datos y sql" in name.lower():
        return "Curso de Fundamentos de Bases de Datos y SQL"
    return name

def parse_metadata(section_content, frontmatter, default_course_name):
    """Extracts Course name, Module name, and Teacher from notes metadata lines."""
    metadata_lines = section_content.split('\n')[:15]
    metadata_text = "\n".join(metadata_lines)
    
    course_name = default_course_name
    course_module = ""
    teacher = ""
    
    # 1. Course Name
    course_match = re.search(r'\*\*Curso:\*\*?\s*(?:\[\[)?([^\]\n\*]+)(?:\]\])?', metadata_text)
    if course_match:
        course_val = course_match.group(1).strip()
        # Clean parentheticals (e.g. "(Módulo 1: ...)")
        mod_match = re.search(r'\s*\((Módulo|Section|Sección)\s*([^)]+)\)', course_val)
        if mod_match:
            course_module = mod_match.group(1) + " " + mod_match.group(2)
            course_name = re.sub(r'\s*\((Módulo|Section|Sección)\s*[^)]+\)', '', course_val).strip()
        else:
            course_name = course_val
            
    # 2. Module (if explicit)
    module_match = re.search(r'\*\*Módulo:\*\*?\s*(?:\[\[)?([^\]\n\*|]+)(?:\]\])?', metadata_text)
    if module_match:
        course_module = module_match.group(1).strip()
        
    # 3. Teacher
    teacher_match = re.search(r'\*\*(?:Instructor|Autor|Instructor/Autor):\*\*?\s*([^|\n\*]+)', metadata_text)
    if teacher_match:
        teacher = teacher_match.group(1).strip()
        if teacher.lower() in ('n/a', 'desconocido', ''):
            teacher = ""
            
    # Clean brackets if any remain
    course_name = course_name.replace('[[', '').replace(']]', '').strip()
    course_module = course_module.replace('[[', '').replace(']]', '').strip()
    
    # Normalize course name
    course_name = normalize_course_name(course_name)
    
    return course_name, course_module, teacher

def parse_note_sections(content):
    """Splits class note body into class_summary and my_notes based on level 2 headings."""
    class_summary = ""
    my_notes = ""
    
    sections = re.split(r'(?=^##\s)', content, flags=re.MULTILINE)
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        first_line = sec.split('\n')[0].lower()
        if 'contexto' in first_line:
            lines = sec.split('\n')[1:]
            class_summary = "\n".join(lines).strip()
        elif 'apuntes' in first_line:
            lines = sec.split('\n')[1:]
            my_notes = "\n".join(lines).strip()
            
    return class_summary, my_notes

def extract_snippets(content):
    """Extracts code blocks and categorizes them into code_snippets or command_snippets."""
    code_snippets = []
    command_snippets = []
    
    pattern = re.compile(r'```(\w*)\n(.*?)\n```', re.DOTALL)
    matches = pattern.findall(content)
    
    cmd_count = 0
    for lang, code in matches:
        lang = lang.lower() if lang else "text"
        code = code.strip()
        
        if lang in ('bash', 'sh', 'shell', 'dockerfile', 'yaml', 'yml'):
            cmd_count += 1
            command_snippets.append({
                "lang": lang,
                "cmd": code,
                "order": str(cmd_count)
            })
        else:
            code_snippets.append({
                "lang": lang,
                "code": code
            })
            
    return code_snippets, command_snippets

def parse_markdown_file(file_path, default_course_name):
    """Parses a markdown file containing one or more class sections."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return []
        
    # Extract file-level frontmatter
    file_frontmatter = {}
    file_frontmatter_yaml = ""
    rest_content = file_content
    
    if file_content.startswith('---'):
        match = re.search(r'^---\n(.*?)\n---\n', file_content, re.DOTALL)
        if match:
            file_frontmatter = parse_yaml_frontmatter(match.group(1))
            file_frontmatter_yaml = match.group(0)
            rest_content = file_content[match.end():]
            
    # Find all headings starting with # and containing 📚
    heading_pattern = re.compile(r'^#\s+(?=.*📚)', re.MULTILINE)
    matches = list(heading_pattern.finditer(rest_content))
    
    if not matches:
        # Check if the file has a main header that we might have missed or it's a MOC
        return []
        
    sections = []
    for i in range(len(matches)):
        start = matches[i].start()
        end = matches[i+1].start() if i + 1 < len(matches) else len(rest_content)
        section_text = rest_content[start:end]
        
        # Check if section ends with a frontmatter block (belonging to next section)
        next_frontmatter = {}
        next_frontmatter_yaml = ""
        fm_at_end_match = re.search(r'\n---\n(.*?)\n---\s*$', section_text, re.DOTALL)
        if fm_at_end_match:
            next_frontmatter = parse_yaml_frontmatter(fm_at_end_match.group(1))
            next_frontmatter_yaml = fm_at_end_match.group(0)
            section_text = section_text[:fm_at_end_match.start()].strip()
            
        sections.append({
            "text": section_text,
            "next_frontmatter": next_frontmatter,
            "next_frontmatter_yaml": next_frontmatter_yaml
        })
        
    classes = []
    current_frontmatter = file_frontmatter
    current_frontmatter_yaml = file_frontmatter_yaml
    
    for sec in sections:
        sec_text = sec["text"]
        heading_line_match = re.match(r'^#\s*(.*?)\n', sec_text)
        if not heading_line_match:
            continue
        raw_title = heading_line_match.group(1)
        class_title = re.sub(r'📚\s*|\s*📚', '', raw_title).strip()
        
        # Clean leading numbers from class_title for order index estimation
        # e.g., "131. Creando el Proyecto" -> order_index = 131
        order_index = 0
        order_match = re.match(r'^(\d+)\.', class_title)
        if order_match:
            order_index = int(order_match.group(1))
            
        content = sec_text[heading_line_match.end():].strip()
        
        course, module, teacher = parse_metadata(content, current_frontmatter, default_course_name)
        class_summary, my_notes = parse_note_sections(content)
        code_snippets, command_snippets = extract_snippets(content)
        
        # Check date in frontmatter
        date_val = parse_date(current_frontmatter.get("fecha"))
        
        # Frontmatter block to prepend
        fm_yaml = current_frontmatter_yaml if current_frontmatter_yaml else (
            f"---\ntipo: fuente\nformato: curso_online\nestado: en_proceso\nfecha: {date_val.strftime('%Y-%m-%d')}\n---\n"
        )
        structured_markdown = f"{fm_yaml}# 📚 {class_title}\n\n{content}"
        
        classes.append({
            "course_name": course,
            "course_module": module,
            "class_title": class_title,
            "teacher": teacher,
            "transcription": content,
            "class_summary": class_summary,
            "my_notes": my_notes,
            "code_snippets": code_snippets,
            "command_snippets": command_snippets,
            "created_at": date_val,
            "order_index": order_index,
            "structured_markdown": structured_markdown
        })
        
        if sec["next_frontmatter"]:
            current_frontmatter = sec["next_frontmatter"]
            current_frontmatter_yaml = sec["next_frontmatter_yaml"].strip() + "\n"
            
    return classes

def import_notes(db: Session, parsed_notes, dry_run=False):
    """Inserts or updates notes in the database using idempotent upsert logic."""
    imported_count = 0
    updated_count = 0
    
    for note_data in parsed_notes:
        course = note_data["course_name"]
        title = note_data["class_title"]
        
        if dry_run:
            print(f"[DRY-RUN] Would process: Course='{course}' | Class='{title}' | Module='{note_data['course_module']}'")
            continue
            
        # Check for existing note
        db_raw = db.query(models.RawNote).filter(
            models.RawNote.course_name == course,
            models.RawNote.class_title == title
        ).first()
        
        if db_raw:
            # Update fields
            db_raw.course_module = note_data["course_module"]
            db_raw.teacher = note_data["teacher"]
            db_raw.transcription = note_data["transcription"]
            db_raw.class_summary = note_data["class_summary"]
            db_raw.my_notes = note_data["my_notes"]
            db_raw.code_snippets = note_data["code_snippets"]
            db_raw.command_snippets = note_data["command_snippets"]
            db_raw.updated_at = datetime.utcnow()
            if note_data["order_index"] > 0:
                db_raw.order_index = note_data["order_index"]
            updated_count += 1
            print(f"Updating: '{course}' -> '{title}'")
        else:
            # Create new
            db_raw = models.RawNote(
                writing_mode="fuente",
                platform="Udemy" if "udemy" in str(note_data["teacher"]).lower() else "",
                course_name=course,
                course_module=note_data["course_module"],
                class_title=title,
                teacher=note_data["teacher"],
                transcription=note_data["transcription"],
                class_summary=note_data["class_summary"],
                my_notes=note_data["my_notes"],
                code_snippets=note_data["code_snippets"],
                command_snippets=note_data["command_snippets"],
                status=models.QueueStatus.PROCESSED,
                created_at=note_data["created_at"],
                updated_at=datetime.utcnow(),
                processed_at=datetime.utcnow(),
                order_index=note_data["order_index"]
            )
            db.add(db_raw)
            db.flush() # Populate ID field
            imported_count += 1
            print(f"Importing: '{course}' -> '{title}'")
            
        # Create or update ProcessedNote
        db_processed = db.query(models.ProcessedNote).filter(
            models.ProcessedNote.raw_note_id == db_raw.id
        ).first()
        
        if db_processed:
            db_processed.structured_markdown = note_data["structured_markdown"]
            db_processed.updated_at = datetime.utcnow()
        else:
            db_processed = models.ProcessedNote(
                raw_note_id=db_raw.id,
                structured_markdown=note_data["structured_markdown"],
                ai_comments="Imported standard note from Sources folder."
            )
            db.add(db_processed)
            db.flush()
            
        db.commit()
        
        # Step 4: Chunk & embed note
        _store_embedding(db, db_processed, db_raw)
        
    print(f"Import process finished. New imports: {imported_count}. Updated existing: {updated_count}.")

def cmd_import(args):
    """Finds all notes under directory and imports them."""
    import_dir = args.dir
    if not os.path.exists(import_dir):
        print(f"ERROR: Import directory not found: {import_dir}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Scanning for markdown notes in {import_dir}...")
    parsed_notes = []
    
    for root, dirs, files in os.walk(import_dir):
        # Skip ANEXOS and standard folders
        if "ANEXOS" in root.split(os.sep):
            continue
            
        for file in files:
            if not file.endswith('.md'):
                continue
                
            # Skip MOC files if they match naming patterns
            file_path = os.path.join(root, file)
            
            # Determine default course name from parent directory or file name
            parent_dir = os.path.basename(root)
            if parent_dir != "" and parent_dir != "02_Fuentes":
                default_course_name = parent_dir
            else:
                default_course_name = os.path.splitext(file)[0]
                
            classes_parsed = parse_markdown_file(file_path, default_course_name)
            if classes_parsed:
                print(f"Parsed {len(classes_parsed)} classes from {file}")
                parsed_notes.extend(classes_parsed)
                
    if not parsed_notes:
        print("No valid note files containing '# 📚' headings were found.")
        return
        
    print(f"Total notes parsed: {len(parsed_notes)}")
    db = SessionLocal()
    try:
        import_notes(db, parsed_notes, dry_run=args.dry_run)
    finally:
        db.close()

# --- Main Entry Point ---

def main():
    parser = argparse.ArgumentParser(description="Database Management Script (Backup, Restore, Import)")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands")
    
    # Backup Command
    backup_parser = subparsers.add_parser("backup", help="Backup PostgreSQL database from Docker")
    backup_parser.add_argument("-f", "--file", help="Custom backup output path (defaults to backups/backup_[timestamp].dump)")
    
    # Restore Command
    restore_parser = subparsers.add_parser("restore", help="Restore PostgreSQL database from a local file")
    restore_parser.add_argument("-f", "--file", required=True, help="Path to the backup dump file")
    
    # Import Command
    import_parser = subparsers.add_parser("import", help="Idempotently parse and import markdown files")
    import_parser.add_argument("-d", "--dir", required=True, help="Directory containing the markdown notes")
    import_parser.add_argument("--dry-run", action="store_true", help="Print actions without modifying database")
    
    args = parser.parse_args()
    
    if args.command == "backup":
        cmd_backup(args)
    elif args.command == "restore":
        cmd_restore(args)
    elif args.command == "import":
        cmd_import(args)

if __name__ == "__main__":
    main()
