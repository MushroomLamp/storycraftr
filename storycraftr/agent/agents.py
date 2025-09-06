import os
import glob
import time
import json
import re
from typing import Any, Dict, List, Optional
import openai
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.progress import Progress
from storycraftr.prompts.story.core import FORMAT_OUTPUT
from storycraftr.utils.core import load_book_config, generate_prompt_with_hash
from storycraftr.utils.core import load_conversation_id, save_conversation_id, clear_conversation_id
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import shutil

load_dotenv()

console = Console()
DEBUG = str(os.getenv("STORYCRAFTR_DEBUG", "")).lower() in ("1", "true", "yes", "on", "debug")

# Store the most recent activity summaries so the UI can surface them without changing
# the signature of generation functions. Keys by thread id and by book path for convenience.
LAST_ACTIVITY_BY_THREAD: Dict[str, str] = {}
LAST_ACTIVITY_BY_BOOK: Dict[str, str] = {}
LAST_EDITED_FILE_BY_BOOK: Dict[str, str] = {}


def get_last_activity_for_book(book_path: str) -> str:
    """Return a concise markdown bullet list describing the last model reasoning/tool calls for the book."""
    try:
        return LAST_ACTIVITY_BY_BOOK.get(str(book_path), "") or ""
    except Exception:
        return ""


def clear_last_activity_for_book(book_path: str) -> None:
    """Clear stored activity for the book (optional utility)."""
    try:
        LAST_ACTIVITY_BY_BOOK.pop(str(book_path), None)
    except Exception:
        pass


def get_last_edited_file_for_book(book_path: str) -> str:
    """Return the last file path (relative to book) that the agent edited with changes > 0."""
    try:
        return LAST_EDITED_FILE_BY_BOOK.get(str(book_path), "") or ""
    except Exception:
        return ""


def _debug(msg: str):
    if DEBUG:
        try:
            console.print(f"[magenta][debug][/magenta] {msg}")
        except Exception:
            pass


def initialize_openai_client(book_path: str):
    """
    Initialize the OpenAI client with the configuration from the book.

    Args:
        book_path (str): Path to the book directory.
    """
    config = load_book_config(book_path)
    api_base = getattr(config, "openai_url", "https://api.openai.com/v1")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=api_base)
    return client


def get_vector_store_id_by_name(assistant_name: str, client) -> str:
    """
    Retrieve the vector store ID by the assistant's name.

    Args:
        assistant_name (str): The name of the assistant.
        client (OpenAI): The OpenAI client.

    Returns:
        str: The ID of the vector store associated with the assistant's name, or None if not found.
    """
    try:
        vector_stores = client.vector_stores.list()
    except Exception as e:
        console.print(
            f"[bold red]Error: The OpenAI API version being used does not support vector stores. Please ensure you are using a compatible version.[/bold red]"
        )
        console.print(f"[bold red]Error details: {str(e)}[/bold red]")
        return None

    expected_name = f"{assistant_name} Docs"
    for vector_store in vector_stores.data:
        if vector_store.name == expected_name:
            return vector_store.id

    console.print(
        f"[bold red]No vector store found with name '{expected_name}'.[/bold red]"
    )
    return None


def upload_markdown_files_to_vector_store(
    vector_store_id: str, book_path: str, client, progress: Progress = None, task=None
):
    """
    Upload all Markdown files from the book directory to the specified vector store.

    Args:
        vector_store_id (str): ID of the vector store to upload files to.
        book_path (str): Path to the book's directory containing markdown files.
        client (OpenAI): The OpenAI client.
        progress (Progress, optional): Progress bar object for tracking progress.
        task (Task, optional): Task ID for progress tracking.

    Returns:
        None
    """
    try:
        vector_stores_api = client.vector_stores
    except Exception as e:
        console.print(
            f"[bold red]Error: The OpenAI API version being used does not support vector stores. Please ensure you are using a compatible version.[/bold red]"
        )
        console.print(f"[bold red]Error details: {str(e)}[/bold red]")
        return

    console.print(
        f"[bold blue]Uploading book content from '{book_path}'...[/bold blue]"
    )
    md_files = load_markdown_files(book_path)

    if not md_files:
        console.print("[bold yellow]No Markdown files found to upload.[/bold yellow]")
        return

    file_streams = [open(file_path, "rb") for file_path in md_files]
    file_batch = vector_stores_api.file_batches.upload_and_poll(
        vector_store_id=vector_store_id, files=file_streams
    )

    # Monitor progress
    while file_batch.status in ["queued", "in_progress"]:
        status_message = f"{file_batch.status}..."
        if progress and task:
            progress.update(task, description=status_message)
        else:
            console.print(f"[bold yellow]{status_message}[/bold yellow]")
        time.sleep(1)

    console.print(
        f"[bold green]Files uploaded successfully to vector store '{vector_store_id}'.[/bold green]"
    )


def load_markdown_files(book_path: str) -> list:
    """
    Load all Markdown files from the book's directory.

    Args:
        book_path (str): Path to the book directory.

    Returns:
        list: A list of valid Markdown file paths.
    """
    console.print(
        f"[bold blue]Loading Markdown files from chapters/ outline/ worldbuilding/ in '{book_path}'...[/bold blue]"
    )
    md_files = glob.glob(os.path.join(book_path, "**", "*.md"), recursive=True)

    allowed_top_dirs = {"chapters", "outline", "worldbuilding"}
    excluded_filenames = {"iterate.md", "chat.md", "getting_started.md"}

    valid_md_files = []
    for file_path in md_files:
        try:
            # Exclude any file inside the storycraftr docs folder
            if os.sep + "storycraftr" + os.sep in file_path:
                continue

            # Ensure the file is under one of the allowed top-level folders
            rel_path = os.path.relpath(file_path, book_path)
            top_component = rel_path.split(os.sep)[0]
            if top_component not in allowed_top_dirs:
                continue

            # Exclude explicitly undesired doc filenames
            if os.path.basename(file_path) in excluded_filenames:
                continue

            with open(file_path, "r", encoding="utf-8") as file:
                if sum(1 for _ in file) > 3:
                    valid_md_files.append(file_path)
        except UnicodeDecodeError:
            console.print(f"[bold red]Error reading file: {file_path}[/bold red]")

    console.print(
        f"[bold green]Loaded {len(valid_md_files)} Markdown files with more than 3 lines from allowed folders.[/bold green]"
    )
    return valid_md_files


def delete_assistant(book_path: str):
    """
    Assistants API is deprecated. This now deletes the associated vector store, if present.

    Args:
        book_path (str): Path to the book directory.

    Returns:
        None
    """
    client = initialize_openai_client(book_path)
    name = os.path.basename(book_path)
    expected_name = f"{name} Docs"
    try:
        vector_stores = client.vector_stores.list()
        for vs in vector_stores.data:
            if getattr(vs, "name", None) == expected_name:
                console.print(f"[bold blue]Deleting vector store '{expected_name}'...[/bold blue]")
                client.vector_stores.delete(vector_store_id=vs.id)
                console.print(
                    f"[bold green]Vector store '{expected_name}' deleted successfully.[/bold green]"
                )
                return
        console.print(f"[bold yellow]No vector store named '{expected_name}' found.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Error deleting resources: {str(e)}[/bold red]")


def create_or_get_assistant(book_path: str):
    """
    Prepare a lightweight assistant configuration for the book using the Responses API.

    Ensures a vector store exists and returns an object with name, model and instructions.

    Args:
        book_path (str): Path to the book directory.
    """
    config = load_book_config(book_path)
    client = initialize_openai_client(book_path)

    openai_model = (
        "gpt-5" if config is None else getattr(config, "openai_model", "gpt-5")
    )

    behavior_file = Path(book_path) / "behaviors" / "default.txt"
    if behavior_file.exists():
        behavior_content = behavior_file.read_text(encoding="utf-8")
    else:
        console.print("[red]Behavior file not found.[/red]")
        return None

    name = Path(book_path).name

    # Ensure vector store exists (create if missing)
    vector_store_id = get_vector_store_id_by_name(name, client)
    if vector_store_id is None:
        try:
            console.print(f"[bold blue]Creating vector store for {name}...[/bold blue]")
            vector_store = client.vector_stores.create(name=f"{name} Docs")

            console.print(f"[bold blue]Loading book files from {book_path}...[/bold blue]")
            upload_markdown_files_to_vector_store(vector_store.id, book_path, client)

            console.print("[bold blue]Waiting for files to be processed...[/bold blue]")
            time.sleep(5)

            vector_store_id = vector_store.id
        except Exception as e:
            console.print(f"[bold red]Error preparing vector store: {str(e)}[/bold red]")
            raise

    # Return a lightweight assistant-like object
    class LightweightAssistant:
        def __init__(self, name: str, model: str, instructions: str):
            self.name = name
            self.model = model
            self.instructions = instructions
            self.id = name  # for backward-compat when code expects .id

    console.print(f"[bold yellow]Using Responses API for assistant '{name}'.[/bold yellow]")
    return LightweightAssistant(name=name, model=openai_model, instructions=behavior_content)


##############################
# Surgical file edit tooling #
##############################

def _normalize_path(book_path: str, path: str) -> Path:
    base = Path(book_path).resolve()
    p = Path(path)
    if not p.is_absolute():
        p = base / p
    p = p.resolve()
    # Ensure edits stay within the book folder
    try:
        p.relative_to(base)
    except Exception:
        raise ValueError("Path is outside of the book directory")
    return p


def _detect_line_ending(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _read_text_file(book_path: str, path: str) -> Dict[str, Any]:
    file_path = _normalize_path(book_path, path)
    if not file_path.exists():
        return {"path": str(file_path), "exists": False, "content": ""}
    content = file_path.read_text(encoding="utf-8")
    return {"path": str(file_path), "exists": True, "content": content}


def _build_anchor_pattern(
    anchor: str,
    *,
    use_regex: bool,
    case_sensitive: bool,
    loose_whitespace: bool,
    normalize_quotes: bool,
):
    if use_regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.compile(anchor, flags)

    pattern = re.escape(anchor)
    if loose_whitespace:
        # Replace any escaped whitespace runs with \s+
        pattern = re.sub(r"\\\s+", r"\\s+", pattern)
        pattern = re.sub(r"(?:\\\s)+", r"\\s+", pattern)
        pattern = re.sub(r"\\\n|\\\r", r"\\s+", pattern)
        pattern = re.sub(r"\\\t", r"\\s+", pattern)
        pattern = pattern.replace(" ", r"\s+")

    if normalize_quotes:
        # Allow curly quotes and dashes variations in target
        pattern = (
            pattern
            .replace(re.escape("\""), r"[\"“”]")
            .replace(re.escape("'"), r"['‘’]")
            .replace(re.escape("-"), r"[-–—]")
        )

    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags)


def _apply_replace_text(
    content: str,
    find: str,
    replace: str,
    *,
    use_regex: bool = False,
    case_sensitive: bool = True,
    loose_whitespace: bool = False,
    normalize_quotes: bool = False,
    occurrence: Optional[int] = None,  # 1-based; None means all
) -> Dict[str, Any]:
    replaced = 0
    new_content = content
    # Use compiled pattern that can be loose on whitespace/quotes
    pattern = _build_anchor_pattern(
        find,
        use_regex=use_regex,
        case_sensitive=case_sensitive,
        loose_whitespace=loose_whitespace,
        normalize_quotes=normalize_quotes,
    )
    if occurrence is None:
        new_content, replaced = pattern.subn(replace, content)
    else:
        cnt = 0
        def _n(m):
            nonlocal cnt, replaced
            cnt += 1
            if cnt == occurrence:
                replaced += 1
                return replace
            return m.group(0)
        new_content = pattern.sub(_n, content)

    return {"content": new_content, "replaced": replaced}


def _apply_replace_between(
    content: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
    *,
    include_markers: bool = False,
    occurrence: Optional[int] = 1,  # default first between pair
    case_sensitive: bool = True,
    loose_whitespace: bool = False,
    normalize_quotes: bool = False,
) -> Dict[str, Any]:
    start_pat = _build_anchor_pattern(
        start_marker,
        use_regex=False,
        case_sensitive=case_sensitive,
        loose_whitespace=loose_whitespace,
        normalize_quotes=normalize_quotes,
    )
    end_pat = _build_anchor_pattern(
        end_marker,
        use_regex=False,
        case_sensitive=case_sensitive,
        loose_whitespace=loose_whitespace,
        normalize_quotes=normalize_quotes,
    )
    start_pos = 0
    for i in range(occurrence or 1):
        m_start = start_pat.search(content, start_pos)
        if not m_start:
            return {"content": content, "replaced": 0}
        m_end = end_pat.search(content, m_start.end())
        if not m_end:
            return {"content": content, "replaced": 0}
        start_pos = m_end.end()
    s0, s1 = m_start.span()
    e0, e1 = m_end.span()
    if include_markers:
        new_content = content[:s0] + replacement + content[e1:]
    else:
        new_content = content[:s1] + replacement + content[e0:]
    return {"content": new_content, "replaced": 1}


def _apply_insert(
    content: str,
    anchor: str,
    insertion: str,
    *,
    position: str = "after",  # "before" | "after"
    occurrence: Optional[int] = 1,
    case_sensitive: bool = True,
    loose_whitespace: bool = False,
    normalize_quotes: bool = False,
) -> Dict[str, Any]:
    pat = _build_anchor_pattern(
        anchor,
        use_regex=False,
        case_sensitive=case_sensitive,
        loose_whitespace=loose_whitespace,
        normalize_quotes=normalize_quotes,
    )
    start = 0
    m = None
    for i in range(occurrence or 1):
        m = pat.search(content, start)
        if not m:
            return {"content": content, "inserted": 0}
        start = m.end()
    if position == "before":
        idx = m.start()
        new_content = content[:idx] + insertion + content[idx:]
    else:
        idx = m.end()
        new_content = content[:idx] + insertion + content[idx:]
    return {"content": new_content, "inserted": 1}


def _fs_apply_text_edits(
    book_path: str,
    path: str,
    edits: List[Dict[str, Any]],
    *,
    create_if_missing: bool = True,
) -> Dict[str, Any]:
    file_path = _normalize_path(book_path, path)
    exists = file_path.exists()
    text = file_path.read_text(encoding="utf-8") if exists else ""
    original_newline = _detect_line_ending(text) if exists else os.linesep
    total_changes = 0
    for edit in edits:
        etype = edit.get("type")
        if etype == "replace_text":
            res = _apply_replace_text(
                text,
                edit.get("find", ""),
                edit.get("replace", ""),
                use_regex=bool(edit.get("use_regex", False)),
                case_sensitive=bool(edit.get("case_sensitive", True)),
                loose_whitespace=bool(edit.get("loose_whitespace", True)),
                normalize_quotes=bool(edit.get("normalize_quotes", True)),
                occurrence=edit.get("occurrence"),
            )
            total_changes += int(res.get("replaced", 0))
            text = res.get("content", text)
        elif etype == "replace_between":
            res = _apply_replace_between(
                text,
                edit.get("start_marker", ""),
                edit.get("end_marker", ""),
                edit.get("replacement", ""),
                include_markers=bool(edit.get("include_markers", False)),
                occurrence=edit.get("occurrence", 1),
                case_sensitive=bool(edit.get("case_sensitive", True)),
                loose_whitespace=bool(edit.get("loose_whitespace", True)),
                normalize_quotes=bool(edit.get("normalize_quotes", True)),
            )
            total_changes += int(res.get("replaced", 0))
            text = res.get("content", text)
        elif etype in ("insert_before", "insert_after"):
            res = _apply_insert(
                text,
                edit.get("anchor", ""),
                edit.get("insert", ""),
                position="before" if etype == "insert_before" else "after",
                occurrence=edit.get("occurrence", 1),
                case_sensitive=bool(edit.get("case_sensitive", True)),
                loose_whitespace=bool(edit.get("loose_whitespace", True)),
                normalize_quotes=bool(edit.get("normalize_quotes", True)),
            )
            total_changes += int(res.get("inserted", 0))
            text = res.get("content", text)
        else:
            # Unknown edit type; skip
            continue

    if not exists and not create_if_missing:
        return {
            "path": str(file_path),
            "created": False,
            "changes": total_changes,
            "preview": text[:2000],
        }

    # Ensure parent dir exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    # Normalize newline endings to original style
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    text_to_write = original_newline.join(normalized)
    file_path.write_text(text_to_write, encoding="utf-8")
    return {
        "path": str(file_path),
        "created": not exists,
        "changes": total_changes,
        "preview": text[:2000],
    }


def _surgical_tools_schema() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "fs_read_text",
            "description": "Read a UTF-8 text file within the current book. Use before editing to get exact anchors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path within the book (e.g., chapters/chapter-1.md)."
                    }
                },
                "required": ["path"],
            },
        },
        {
            "type": "function",
            "name": "fs_apply_text_edits",
            "description": "Apply surgical text edits to a file (replace text, replace between markers, insert before/after). Create file if missing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target file path relative to book."},
                    "create_if_missing": {"type": "boolean", "default": True},
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "oneOf": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["replace_text"]},
                                        "find": {"type": "string"},
                                        "replace": {"type": "string"},
                                        "use_regex": {"type": "boolean", "default": False},
                                        "case_sensitive": {"type": "boolean", "default": True},
                                        "loose_whitespace": {"type": "boolean", "default": True},
                                        "normalize_quotes": {"type": "boolean", "default": True},
                                        "occurrence": {"type": "integer", "minimum": 1}
                                    },
                                    "required": ["type", "find", "replace"]
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["replace_between"]},
                                        "start_marker": {"type": "string"},
                                        "end_marker": {"type": "string"},
                                        "replacement": {"type": "string"},
                                        "include_markers": {"type": "boolean", "default": False},
                                        "occurrence": {"type": "integer", "minimum": 1},
                                        "case_sensitive": {"type": "boolean", "default": True},
                                        "loose_whitespace": {"type": "boolean", "default": True},
                                        "normalize_quotes": {"type": "boolean", "default": True}
                                    },
                                    "required": ["type", "start_marker", "end_marker", "replacement"]
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["insert_before", "insert_after"]},
                                        "anchor": {"type": "string"},
                                        "insert": {"type": "string"},
                                        "occurrence": {"type": "integer", "minimum": 1},
                                        "case_sensitive": {"type": "boolean", "default": True},
                                        "loose_whitespace": {"type": "boolean", "default": True},
                                        "normalize_quotes": {"type": "boolean", "default": True}
                                    },
                                    "required": ["type", "anchor", "insert"]
                                }
                            ]
                        }
                    }
                },
                "required": ["path", "edits"],
            },
        },
    ]


def create_message(
    book_path: str,
    thread_id: str,
    content: str,
    assistant,
    file_path: str = None,
    progress: Progress = None,
    task_id=None,
) -> str:
    """
    Create a message in the thread and return a single complete response.

    Args:
        book_path (str): Path to the book directory.
        thread_id (str): ID of the thread where the message will be created.
        content (str): The content of the message.
        assistant (object): The assistant object with an ID.
        file_path (str, optional): The path to a file to attach as an attachment. Defaults to None.
        progress (Progress, optional): Progress object for tracking. Defaults to None.
        task_id (int, optional): Task ID for the progress bar.

    Returns:
        str: The generated response text from the assistant.
    """
    client = initialize_openai_client(book_path)
    config = load_book_config(book_path)
    should_print = progress is None

    internal_progress = False
    if progress is None:
        progress = Progress()
        task_id = progress.add_task("[cyan]Waiting for assistant response...", total=50)
        internal_progress = True

    if should_print:
        console.print(
            f"[bold blue]Creating response (thread {thread_id})...[/bold blue]"
        )

    if file_path and os.path.exists(file_path):
        if should_print:
            console.print(
                f"[bold blue]Reading content from {file_path} for improvement...[/bold blue]"
            )
        with open(file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
            # Create/overwrite backup of existing file as .md.back (or .back if not .md)
            try:
                backup_path = file_path + ".back"
                if file_path.lower().endswith(".md"):
                    backup_path = file_path + ".back"
                # Ensure parent dir exists, then copy
                shutil.copyfile(file_path, backup_path)
                _debug(f"Backed up '{file_path}' to '{backup_path}'.")
            except Exception as be:
                _debug(f"Backup failed for '{file_path}': {be}")
            # Encourage tool usage for surgical edits
            rel_path = None
            try:
                rel_path = os.path.relpath(file_path, book_path)
            except Exception:
                rel_path = file_path
            tool_guidance = (
                "You can modify existing files using tools. When editing an existing file, prefer making surgical edits via fs_read_text and fs_apply_text_edits instead of outputting the entire file.\n"
                f"Target file (relative to book): {rel_path}. Steps: 1) fs_read_text to get current text, 2) decide minimal changes, 3) fs_apply_text_edits with precise edits (replace_text, replace_between, insert_before/insert_after)."
            )
            content = (
                f"{tool_guidance}\n\nHere is the existing content to improve (for context):\n{file_content}\n\n{content}"
            )
            _debug(f"Editing existing file detected; advising tool usage for '{rel_path}'.")
    else:
        if should_print:
            console.print(
                f"[bold blue]Using provided prompt to generate new content...[/bold blue]"
            )

    # Generar el prompt con hash
    prompt_with_hash = generate_prompt_with_hash(
        f"{FORMAT_OUTPUT.format(reference_author=config.reference_author, language=config.primary_language)}\n\n{content}",
        datetime.now().strftime("%B %d, %Y"),
        book_path=book_path,
    )

    try:
        if internal_progress:
            progress.start()

        # Helper to extract text robustly from Responses API
        def _extract_text(resp) -> str:
            # Prefer convenience property if present
            for attr in ("output_text",):
                try:
                    val = getattr(resp, attr)
                    if isinstance(val, str) and val:
                        return val
                except Exception:
                    pass
            # Fallback to dict parsing for generic shapes
            data = None
            # Accept raw dicts from HTTP fallback
            if isinstance(resp, dict):
                data = resp
            for to_dict in (getattr(resp, "model_dump", None), getattr(resp, "to_dict", None)):
                try:
                    if callable(to_dict):
                        data = to_dict()
                        break
                except Exception:
                    pass
            if not isinstance(data, dict):
                return ""
            if isinstance(data.get("output_text"), str):
                return data["output_text"]
            # Helper: deduplicate while preserving order
            def _dedup_preserve_order(chunks: list[str]) -> list[str]:
                seen: set[str] = set()
                result: list[str] = []
                for chunk in chunks:
                    if not isinstance(chunk, str):
                        continue
                    s = chunk.strip()
                    if not s:
                        continue
                    if s in seen:
                        continue
                    # Avoid immediate repeats differing only by whitespace
                    if result and s == result[-1].strip():
                        continue
                    seen.add(s)
                    result.append(chunk)
                return result

            output_text_chunks = []
            text_value_chunks = []
            output = data.get("output")
            if isinstance(output, list):
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    contents = item.get("content")
                    if isinstance(contents, list):
                        for c in contents:
                            if not isinstance(c, dict):
                                continue
                            # Example structure: {"type": "output_text", "text": "..."}
                            if c.get("type") == "output_text" and isinstance(c.get("text"), str):
                                output_text_chunks.append(c.get("text"))
                            # Older structure: {"type": "text", "text": {"value": "..."}}
                            elif c.get("type") == "text":
                                inner = c.get("text")
                                if isinstance(inner, dict) and isinstance(inner.get("value"), str):
                                    text_value_chunks.append(inner.get("value"))
            # Prefer output_text chunks if present; else fall back to text.value
            if output_text_chunks:
                deduped = _dedup_preserve_order(output_text_chunks)
                return "\n".join(deduped)
            if text_value_chunks:
                deduped = _dedup_preserve_order(text_value_chunks)
                return "\n".join(deduped)
            return ""

        # Compose base instruction + user input
        base_instructions = assistant.instructions if hasattr(assistant, "instructions") else ""
        vector_store_id = get_vector_store_id_by_name(assistant.name, client)

        def _create_response(input_items):
            tools: List[Dict[str, Any]] = (
                [{"type": "file_search", "vector_store_ids": [vector_store_id]}]
                if vector_store_id
                else [{"type": "file_search"}]
            )
            tools.extend(_surgical_tools_schema())
            kwargs = dict(
                model=assistant.model,
                input=input_items,
                instructions=base_instructions,
                #temperature=0.7,
                top_p=1.0,
                tools=tools,
                tool_choice="auto",
            )
            _debug("Creating response with tools: file_search + surgical (fs_read_text, fs_apply_text_edits)")
            return client.responses.create(**kwargs)

        def _extract_tool_calls(resp) -> List[Dict[str, Any]]:
            data = None
            # Accept raw dicts or SDK objects
            if isinstance(resp, dict):
                data = resp
            else:
                for to_dict in (getattr(resp, "model_dump", None), getattr(resp, "to_dict", None)):
                    try:
                        if callable(to_dict):
                            data = to_dict()
                            break
                    except Exception:
                        pass
            if not isinstance(data, dict):
                return []
            calls: List[Dict[str, Any]] = []
            # Pattern 1: Output contains function_call/tool_use items
            output = data.get("output")
            if isinstance(output, list):
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    t = item.get("type")
                    if t in ("function_call", "tool_use"):
                        name = item.get("name") or (item.get("function", {}) or {}).get("name")
                        args = item.get("arguments") or (item.get("function", {}) or {}).get("arguments")
                        call_id = (
                            item.get("call_id")
                            or item.get("id")
                            or (item.get("function", {}) or {}).get("id")
                        )
                        if name and call_id:
                            calls.append({"name": name, "arguments": args, "call_id": call_id})
            # Pattern 2: required_action submit_tool_outputs
            ra = data.get("required_action") or {}
            ra_type = ra.get("type")
            if ra_type == "submit_tool_outputs":
                tool_calls = (
                    (ra.get("submit_tool_outputs") or {}).get("tool_calls")
                    or ra.get("tool_calls")
                    or []
                )
                for c in tool_calls:
                    if not isinstance(c, dict):
                        continue
                    fn = c.get("function") or {}
                    name = fn.get("name") or c.get("name")
                    args = fn.get("arguments") or c.get("arguments")
                    call_id = c.get("id") or c.get("tool_call_id") or c.get("call_id")
                    if name and call_id:
                        calls.append({"name": name, "arguments": args, "call_id": call_id})
            return calls

        # Track applied edits and activity for UI summary
        tool_edit_invocations = {"fs_apply_text_edits": 0, "changes": 0}
        activity_lines: List[str] = []

        def _resolve_tools_loop(input_items, last_response):
            response_obj = last_response
            safety_counter = 0
            while True:
                safety_counter += 1
                if safety_counter > 8:
                    break
                # Append the model's output (including reasoning and function_call items)
                try:
                    if hasattr(response_obj, "output") and isinstance(response_obj.output, list):
                        input_items += response_obj.output
                    else:
                        data = response_obj if isinstance(response_obj, dict) else None
                        if data is None:
                            for to_dict in (getattr(response_obj, "model_dump", None), getattr(response_obj, "to_dict", None)):
                                if callable(to_dict):
                                    try:
                                        data = to_dict()
                                        break
                                    except Exception:
                                        pass
                        if isinstance(data, dict) and isinstance(data.get("output"), list):
                            input_items += data.get("output")
                except Exception:
                    pass

                calls = _extract_tool_calls(response_obj)
                if calls:
                    _debug(f"Model requested {len(calls)} tool call(s): " + ", ".join([c.get("name") or "?" for c in calls]))
                if not calls:
                    break

                # Execute tools and append function_call_output items
                for call in calls:
                    try:
                        name = call.get("name")
                        args_raw = call.get("arguments") or "{}"
                        try:
                            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                        except Exception:
                            args = {}
                        if DEBUG:
                            args_preview = json.dumps(args)[:300]
                            _debug(f"Calling tool {name} with args {args_preview}...")
                        # Log the tool call succinctly for UI
                        try:
                            args_preview_ui = json.dumps(args)
                            if len(args_preview_ui) > 200:
                                args_preview_ui = args_preview_ui[:200] + "..."
                            activity_lines.append(f"tool: {name} args={args_preview_ui}")
                        except Exception:
                            pass
                        if name == "fs_read_text":
                            result = _read_text_file(book_path, args.get("path", ""))
                        elif name == "fs_apply_text_edits":
                            # Before applying edits, ensure backup exists for the target file if it already exists
                            try:
                                target_rel = args.get("path", "") or ""
                                target_abs = _normalize_path(book_path, target_rel)
                                if target_abs.exists():
                                    backup_abs = Path(str(target_abs) + ".back")
                                    shutil.copyfile(str(target_abs), str(backup_abs))
                            except Exception as be:
                                _debug(f"Backup before edits failed for '{args.get('path', '')}': {be}")
                            result = _fs_apply_text_edits(
                                book_path,
                                args.get("path", ""),
                                args.get("edits", []) or [],
                                create_if_missing=bool(args.get("create_if_missing", True)),
                            )
                            try:
                                tool_edit_invocations["fs_apply_text_edits"] += 1
                                tool_edit_invocations["changes"] += int(result.get("changes", 0))
                                # Track last edited file (only if changes > 0)
                                if int(result.get("changes", 0)) > 0:
                                    try:
                                        # Normalize and store relative path
                                        norm_abs = _normalize_path(book_path, args.get("path", ""))
                                        rel = os.path.relpath(str(norm_abs), book_path)
                                        LAST_EDITED_FILE_BY_BOOK[str(book_path)] = rel
                                    except Exception:
                                        LAST_EDITED_FILE_BY_BOOK[str(book_path)] = args.get("path", "")
                            except Exception:
                                pass
                        else:
                            result = {"error": f"Unknown tool: {name}"}
                        if DEBUG:
                            res_preview = json.dumps(result)[:300]
                            _debug(f"Tool {name} -> {res_preview}")
                        input_items.append({
                            "type": "function_call_output",
                            "call_id": call.get("call_id"),
                            "output": json.dumps(result),
                        })
                    except Exception as e:
                        input_items.append({
                            "type": "function_call_output",
                            "call_id": call.get("call_id"),
                            "output": json.dumps({"error": str(e)}),
                        })

                # Ask the model to continue with tool outputs available
                response_obj = _create_response(input_items)
            return response_obj

        # Seed the input sequence with the user's request
        input_items: List[Dict[str, Any]] = [
            {"role": "user", "content": prompt_with_hash}
        ]

        # First response and tool resolution
        response = _create_response(input_items)
        response = _resolve_tools_loop(input_items, response)
        response_text = _extract_text(response)

        # Build activity summary from the final response object
        def _to_dict(obj) -> Dict[str, Any]:
            if isinstance(obj, dict):
                return obj
            for to_dict in (getattr(obj, "model_dump", None), getattr(obj, "to_dict", None)):
                try:
                    if callable(to_dict):
                        return to_dict()
                except Exception:
                    pass
            return {}

        try:
            data = _to_dict(response)
            # Reasoning summary (if present)
            reasoning = data.get("reasoning") or {}
            reason_summary = reasoning.get("summary")
            if isinstance(reason_summary, str) and reason_summary.strip():
                activity_lines.insert(0, f"reasoning: {reason_summary.strip()}")
            # File search calls and function calls in output
            output_items = data.get("output") or []
            for item in output_items:
                try:
                    if not isinstance(item, dict):
                        continue
                    t = item.get("type")
                    if t == "file_search_call":
                        queries = item.get("queries") or []
                        if queries:
                            activity_lines.append("file_search: " + ", ".join([str(q) for q in queries]))
                    elif t in ("function_call", "tool_use"):
                        nm = item.get("name")
                        args = item.get("arguments")
                        if isinstance(args, str):
                            argsp = args
                        else:
                            argsp = json.dumps(args or {})
                        if len(argsp) > 200:
                            argsp = argsp[:200] + "..."
                        activity_lines.append(f"model_call: {nm} args={argsp}")
                except Exception:
                    pass
        except Exception:
            pass

        # Append edit summary if applicable
        try:
            if tool_edit_invocations["fs_apply_text_edits"] > 0:
                activity_lines.append(
                    f"applied_edits: {tool_edit_invocations['fs_apply_text_edits']} call(s), changes={tool_edit_invocations['changes']}"
                )
        except Exception:
            pass

        activity_md = "\n".join(f"- {line}" for line in activity_lines) if activity_lines else ""
        # Persist for UI retrieval
        try:
            LAST_ACTIVITY_BY_THREAD[str(thread_id)] = activity_md
            LAST_ACTIVITY_BY_BOOK[str(book_path)] = activity_md
        except Exception:
            pass
        if DEBUG:
            _debug(f"Initial response text len={len(response_text)}")

        if internal_progress:
            progress.stop()

        if DEBUG:
            _debug(
                f"Tool edit summary: fs_apply_text_edits calls={tool_edit_invocations['fs_apply_text_edits']}, total changes={tool_edit_invocations['changes']}"
            )
            if tool_edit_invocations["fs_apply_text_edits"] == 0:
                _debug("No surgical edits were applied. If the file existed, saving may have been skipped.")
        return response_text

    except Exception as e:
        console.print(f"[bold red]Error creating message: {str(e)}[/bold red]")
        raise


def get_thread(book_path: str, agent_name: str | None = None):
    """
    Create a conversation compatible with the Responses API.

    Args:
        book_path (str): Path to the book directory.

    Returns:
        object: An object with an "id" attribute starting with 'conv_'.
    """
    client = initialize_openai_client(book_path)

    # Try to reuse a persisted conversation id for this book
    existing_id = load_conversation_id(book_path, agent_name)
    if existing_id:
        class ConversationWrapper:
            def __init__(self, id: str):
                self.id = id
        return ConversationWrapper(existing_id)

    # Otherwise create a new conversation and persist it
    conversation = client.conversations.create()
    try:
        if agent_name:
            save_conversation_id(book_path, conversation.id, agent_name)
    except Exception:
        pass
    class ConversationWrapper:
        def __init__(self, id: str):
            self.id = id
    return ConversationWrapper(conversation.id)


def reset_conversation(book_path: str, agent_name: str | None = None) -> None:
    """Explicitly clear the persisted conversation for this agent so a fresh one is created next run."""
    try:
        clear_conversation_id(book_path, agent_name)
        console.print(
            f"[bold yellow]Cleared persisted conversation for agent '{agent_name or ''}'. A new one will be created on next call.[/bold yellow]"
        )
    except Exception as e:
        console.print(f"[bold red]Failed to clear conversation: {e}[/bold red]")


def delete_file(vector_stores_api, files_api, vector_store_id, file_id):
    """Delete a single file from the vector store and from global files storage."""
    # First, detach from the vector store
    try:
        vector_stores_api.files.delete(vector_store_id=vector_store_id, file_id=file_id)
    except Exception as e:
        console.print(f"[bold red]Error detaching file {file_id} from vector store: {str(e)}[/bold red]")
    # Then, remove from the files storage to avoid leaks
    try:
        # Some SDKs accept positional or keyword argument
        try:
            files_api.delete(file_id)
        except TypeError:
            files_api.delete(file_id=file_id)
    except Exception as e:
        console.print(f"[bold red]Error deleting file {file_id} from files storage: {str(e)}[/bold red]")


def delete_files_in_parallel(vector_stores_api, files_api, vector_store_id, files):
    """Delete multiple files from the vector store and global files storage in parallel."""
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(delete_file, vector_stores_api, files_api, vector_store_id, file.id)
            for file in files.data
        ]
        # Wait for all tasks to complete
        for future in futures:
            future.result()


def update_agent_files(book_path: str, assistant):
    """
    Update the assistant's knowledge with new files from the book path.

    Args:
        book_path (str): Path to the book directory.
        assistant (object): The assistant object.
    """
    client = initialize_openai_client(book_path)
    assistant_name = assistant.name
    vector_store_id = get_vector_store_id_by_name(assistant_name, client)

    if not vector_store_id:
        console.print(
            f"[bold red]Error: Could not find vector store for assistant '{assistant_name}'.[/bold red]"
        )
        return

    try:
        # Obtener los archivos actuales del vector store
        vector_stores_api = client.vector_stores
        files_api = client.files
        files = vector_stores_api.files.list(vector_store_id=vector_store_id)

        # Eliminar archivos en paralelo (vector store + files storage)
        if files.data:
            console.print(
                f"[bold blue]Deleting {len(files.data)} old files from vector store and files storage...[/bold blue]"
            )
            delete_files_in_parallel(vector_stores_api, files_api, vector_store_id, files)

        # Cargar archivos del libro
        console.print(f"[bold blue]Loading book files from {book_path}...[/bold blue]")
        upload_markdown_files_to_vector_store(vector_store_id, book_path, client)

        console.print(
            f"[bold green]Files updated successfully in assistant '{assistant.name}'.[/bold green]"
        )
    except Exception as e:
        console.print(f"[bold red]Error updating files: {str(e)}[/bold red]")
        raise


def process_chapters(
    save_to_markdown,
    book_path: str,
    prompt_template: str,
    task_description: str,
    file_suffix: str,
    agent_name: str | None = None,
    **prompt_kwargs,
):
    """
    Process each chapter of the book with the given prompt template and generate output.

    Args:
        save_to_markdown (function): Function to save the output to a markdown file.
        book_path (str): Path to the book directory.
        prompt_template (str): The template for the prompt.
        task_description (str): Description of the task for progress display.
        file_suffix (str): Suffix for the output file.
        **prompt_kwargs: Additional arguments for the prompt template.
    """
    # Directories to process
    chapters_dir = os.path.join(book_path, "chapters")
    outline_dir = os.path.join(book_path, "outline")
    worldbuilding_dir = os.path.join(book_path, "worldbuilding")

    # Check if directories exist
    for dir_path in [chapters_dir, outline_dir, worldbuilding_dir]:
        if not os.path.exists(dir_path):
            raise FileNotFoundError(f"The directory '{dir_path}' does not exist.")

    # Files to exclude
    excluded_files = ["cover.md", "back-cover.md"]

    # Get Markdown files from each directory, excluding the unwanted files
    files_to_process = []
    for dir_path in [chapters_dir, outline_dir, worldbuilding_dir]:
        files = [
            f
            for f in os.listdir(dir_path)
            if f.endswith(".md") and f not in excluded_files
        ]
        files_to_process.extend([os.path.join(dir_path, f) for f in files])

    if not files_to_process:
        raise FileNotFoundError(
            "No Markdown (.md) files were found in the chapter directory."
        )

    with Progress() as progress:
        task_chapters = progress.add_task(
            f"[cyan]{task_description}", total=len(files_to_process)
        )
        task_openai = progress.add_task("[green]Calling OpenAI...", total=1)

        for chapter_file in files_to_process:
            chapter_path = os.path.join(chapters_dir, chapter_file)
            prompt = prompt_template.format(**prompt_kwargs)

            assistant = create_or_get_assistant(book_path)
            thread = get_thread(book_path, agent_name=agent_name)

            progress.reset(task_openai)
            refined_text = create_message(
                book_path,
                thread_id=thread.id,
                content=prompt,
                assistant=assistant,
                progress=progress,
                task_id=task_openai,
                file_path=chapter_path,
            )

            save_to_markdown(
                book_path,
                os.path.join("chapters", chapter_file),
                file_suffix,
                refined_text,
                progress=progress,
                task=task_chapters,
            )
            progress.update(task_chapters, advance=1)

    update_agent_files(book_path, assistant)
