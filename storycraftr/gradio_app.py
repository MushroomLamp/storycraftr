import os
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple

import gradio as gr
from rich.console import Console
from difflib import HtmlDiff
import html as _html

# Direct imports to call the application logic without shelling out to the CLI
from storycraftr.init import init_structure_story
from storycraftr.utils.core import load_book_config
from storycraftr.agent.agents import (
    create_or_get_assistant,
    update_agent_files,
    get_last_activity_for_book,
    delete_assistant,
)
from storycraftr.agent.agents import get_last_edited_file_for_book
from storycraftr.utils.pdf import to_pdf

# Story agent functions
from storycraftr.agent.story.outline import (
    generate_general_outline,
    generate_character_summary,
    generate_plot_points,
    generate_chapter_synopsis,
)
from storycraftr.agent.story.worldbuilding import (
    generate_history,
    generate_geography,
    generate_culture,
    generate_magic_system,
    generate_technology,
)
from storycraftr.agent.story.chapters import (
    generate_chapter,
    generate_cover,
    generate_back_cover,
)
from storycraftr.agent.story.iterate import (
    iterate_check_names,
    fix_name_in_chapters,
    refine_character_motivation,
    strengthen_core_argument,
    insert_new_chapter,
    check_consistency_across,
)

 

console = Console()

BOOKS_DIR = Path(os.getenv("BOOKS_CONTAINER_DIR", "/workspace/books"))
CLI = os.getenv("STORYCRAFTR_CLI", "storycraftr")


# ----------------------------- Helpers ---------------------------------

# Contextual help for commands shown in UI
OUTLINE_HELP: dict[str, str] = {
    "general-outline": (
        "**general-outline**: Generate a high-level plot overview for the whole book.\n\n"
        "- Output: `outline/general_outline.md`\n"
        "- Use the Prompt to describe scope/tone/themes.\n\n"
        "Example CLI:```bash\nstorycraftr outline general-outline \"Your overall story premise...\"\n```"
    ),
    "character-summary": (
        "**character-summary**: Summarize main characters, roles, arcs, and relationships.\n\n"
        "- Output: `outline/character_summary.md`\n"
        "- Use the Prompt to list characters or desired focus.\n\n"
        "Example CLI:```bash\nstorycraftr outline character-summary \"Summarize Zevid and the ruling families...\"\n```"
    ),
    "plot-points": (
        "**plot-points**: Identify key beats/events across the narrative.\n\n"
        "- Output: `outline/plot_points.md`\n"
        "- Use the Prompt to specify structure (acts/arcs) if desired.\n\n"
        "Example CLI:```bash\nstorycraftr outline plot-points \"List turning points and midpoint reversal...\"\n```"
    ),
    "chapter-synopsis": (
        "**chapter-synopsis**: Produce chapter-by-chapter summaries with goals, stakes, and outcomes.\n\n"
        "- Output: `outline/chapter_synopsis.md`\n"
        "- Use the Prompt to guide length/number of chapters.\n\n"
        "Example CLI:```bash\nstorycraftr outline chapter-synopsis \"Outline 20 chapters for a dystopian heist...\"\n```"
    ),
}

WORLD_HELP: dict[str, str] = {
    "history": (
        "**history**: Describe historical timelines, conflicts, and milestones of the setting.\n\n"
        "- Output: `worldbuilding/history.md`\n\n"
        "Example CLI:```bash\nstorycraftr worldbuilding history \"From pre-collapse to present factions...\"\n```"
    ),
    "geography": (
        "**geography**: Define regions, climates, resources, and strategic locations.\n\n"
        "- Output: `worldbuilding/geography.md`\n\n"
        "Example CLI:```bash\nstorycraftr worldbuilding geography \"Key city-states, wastelands, and trade routes...\"\n```"
    ),
    "culture": (
        "**culture**: Explore customs, norms, rituals, power structures, and daily life.\n\n"
        "- Output: `worldbuilding/culture.md`\n\n"
        "Example CLI:```bash\nstorycraftr worldbuilding culture \"Elite rites vs. worker traditions...\"\n```"
    ),
    "technology": (
        "**technology**: Explain tools, capabilities, and constraints; how tech shapes society.\n\n"
        "- Output: `worldbuilding/technology.md`\n\n"
        "Example CLI:```bash\nstorycraftr worldbuilding technology \"Bio/nano interfaces, augmentation risks...\"\n```"
    ),
    "magic-system": (
        "**magic-system**: Define rules/limitations of the system (science-as-magic or magic).\n\n"
        "- Output: `worldbuilding/magic_system.md`\n\n"
        "Example CLI:```bash\nstorycraftr worldbuilding magic-system \"Costs, sources, and boundaries of power...\"\n```"
    ),
}

def run_cli(args: List[str], cwd: str | None = None) -> Tuple[str, int]:
    # Deprecated: retained for backwards compatibility if needed.
    try:
        console.print(f"[bold blue]Running:[/bold blue] {CLI} {' '.join(args)} cwd={cwd or os.getcwd()}")
        proc = subprocess.run([CLI, *args], capture_output=True, text=True, cwd=cwd)  # nosec
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        console.print(f"[bold blue]Exit code:[/bold blue] {proc.returncode}")
        return output.strip(), proc.returncode
    except Exception as e:
        console.print(f"[bold red]Subprocess error:[/bold red] {e}")
        return f"Error: {e}", 1


def list_books() -> List[str]:
    if not BOOKS_DIR.exists():
        return []
    names: List[str] = []
    for child in BOOKS_DIR.iterdir():
        if child.is_dir():
            names.append(child.name)
    names.sort()
    return names


def book_path(book_name: str) -> Path:
    return BOOKS_DIR / book_name


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_text_file(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"


def write_text_file(file_path: Path, content: str) -> str:
    try:
        ensure_dir(file_path.parent)
        file_path.write_text(content or "", encoding="utf-8")
        return "Saved."
    except Exception as e:
        return f"Error saving file: {e}"


def delete_book(book_name: str) -> str:
    try:
        target = book_path(book_name)
        if target.exists() and target.is_dir():
            # Attempt to delete associated vector store first (best-effort)
            try:
                delete_assistant(str(target))
            except Exception as _e:
                # Proceed with local deletion even if remote deletion fails
                pass
            shutil.rmtree(target)
            return f"Deleted book and associated vector store (if any): {book_name}"
        return "Book not found."
    except Exception as e:
        return f"Error deleting book: {e}"


def get_book_files(root: Path) -> List[str]:
    rels: List[str] = []
    if not root.exists():
        return rels
    for path in root.rglob("*"):
        if path.is_file() and (
            path.suffix.lower() in {".md", ".txt", ".json", ".tex"}
            or path.name in {"storycraftr.json", "papercraftr.json"}
        ):
            try:
                rels.append(str(path.relative_to(root)))
            except Exception:
                pass

    # Suggest common files even if they don't exist yet, so users can create/edit them directly
    suggested = [
        "outline/general_outline.md",
        "outline/character_summary.md",
        "outline/plot_points.md",
        "outline/chapter_synopsis.md",
        "worldbuilding/history.md",
        "worldbuilding/geography.md",
        "worldbuilding/culture.md",
        "worldbuilding/technology.md",
        "worldbuilding/magic_system.md",
        "chapters/cover.md",
        "chapters/back-cover.md",
        "chapters/epilogue.md",
    ]
    existing = set(rels)
    for s in suggested:
        if s not in existing:
            rels.append(s)

    rels.sort()
    return rels


def list_chapter_files(root: Path) -> List[str]:
    rels: List[str] = []
    chapters_dir = root / "chapters"
    if not chapters_dir.exists():
        return rels
    for path in chapters_dir.rglob("*.md"):
        try:
            rels.append(str(path.relative_to(root)))
        except Exception:
            pass
    rels.sort()
    return rels


# ----------------------------- Diff Helpers ---------------------------------

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"


def _backup_path_for(path: Path) -> Path:
    return Path(str(path) + ".back")


def _diff_html(old_text: str, new_text: str, left_label: str, right_label: str) -> str:
    try:
        from difflib import SequenceMatcher

        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        def esc(s: str) -> str:
            return _html.escape(s, quote=False)

        def intraline(a: str, b: str) -> Tuple[str, str]:
            sm = SequenceMatcher(None, a, b)
            a_out = []
            b_out = []
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    a_out.append(esc(a[i1:i2]))
                    b_out.append(esc(b[j1:j2]))
                elif tag == "delete":
                    a_out.append(f"<span class=\"tok-del\">{esc(a[i1:i2])}</span>")
                elif tag == "insert":
                    b_out.append(f"<span class=\"tok-ins\">{esc(b[j1:j2])}</span>")
                elif tag == "replace":
                    a_out.append(f"<span class=\"tok-del\">{esc(a[i1:i2])}</span>")
                    b_out.append(f"<span class=\"tok-ins\">{esc(b[j1:j2])}</span>")
            return "".join(a_out) or "&nbsp;", "".join(b_out) or "&nbsp;"

        sm = SequenceMatcher(None, old_lines, new_lines)
        rows = []
        l_old = 1
        l_new = 1

        def add_row(cls: str, ln_l: str, left_html: str, ln_r: str, right_html: str):
            rows.append(
                f"<tr class=\"{cls}\">"
                f"<td class=\"lnum\">{ln_l}</td><td class=\"cell\">{left_html}</td>"
                f"<td class=\"lnum\">{ln_r}</td><td class=\"cell\">{right_html}</td>"
                f"</tr>"
            )

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    left = esc(old_lines[i1 + k]) or "&nbsp;"
                    right = esc(new_lines[j1 + k]) or "&nbsp;"
                    add_row("same", str(l_old), left, str(l_new), right)
                    l_old += 1
                    l_new += 1
            elif tag == "delete":
                for k in range(i2 - i1):
                    left = esc(old_lines[i1 + k]) or "&nbsp;"
                    add_row("removed", str(l_old), left, "", "&nbsp;")
                    l_old += 1
            elif tag == "insert":
                for k in range(j2 - j1):
                    right = esc(new_lines[j1 + k]) or "&nbsp;"
                    add_row("added", "", "&nbsp;", str(l_new), right)
                    l_new += 1
            elif tag == "replace":
                len_l = i2 - i1
                len_r = j2 - j1
                max_len = max(len_l, len_r)
                for k in range(max_len):
                    left_raw = old_lines[i1 + k] if k < len_l else ""
                    right_raw = new_lines[j1 + k] if k < len_r else ""
                    if left_raw and right_raw:
                        left_h, right_h = intraline(left_raw, right_raw)
                        add_row("changed", str(l_old), left_h, str(l_new), right_h)
                        l_old += 1
                        l_new += 1
                    elif left_raw and not right_raw:
                        add_row("removed", str(l_old), esc(left_raw) or "&nbsp;", "", "&nbsp;")
                        l_old += 1
                    elif right_raw and not left_raw:
                        add_row("added", "", "&nbsp;", str(l_new), esc(right_raw) or "&nbsp;")
                        l_new += 1

        styles = """
<style>
  .sc-diff { max-height: 60vh; overflow: auto; background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 6px; }
  .sc-diff table { width: 100%; table-layout: fixed; border-collapse: collapse; color: #d4d4d4; font-size: 13px; }
  .sc-diff thead th { position: sticky; top: 0; background: #2d2d2d; z-index: 1; color: #c5c5c5; }
  .sc-diff th, .sc-diff td { border-bottom: 1px solid #2a2a2a; padding: 2px 6px; vertical-align: top; }
  .sc-diff .lnum { width: 3.5ch; text-align: right; color: #858585; border-right: 1px solid #2a2a2a; }
  .sc-diff .cell { white-space: pre-wrap; overflow-wrap: anywhere; }
  .sc-diff tr.same .cell { background: transparent; }
  .sc-diff tr.added .cell { background: rgba(76, 175, 80, 0.18); }
  .sc-diff tr.removed .cell { background: rgba(244, 67, 54, 0.18); }
  .sc-diff tr.changed .cell { background: rgba(255, 193, 7, 0.16); }
  .sc-diff .tok-ins { background: rgba(76, 175, 80, 0.35); }
  .sc-diff .tok-del { background: rgba(244, 67, 54, 0.35); }
</style>
"""
        header = (
            f"<thead><tr>"
            f"<th class='lnum'></th><th>{_html.escape(left_label)}</th>"
            f"<th class='lnum'></th><th>{_html.escape(right_label)}</th>"
            f"</tr></thead>"
        )
        body = "<tbody>" + "".join(rows) + "</tbody>"
        return f"{styles}<div class=\"sc-diff\"><table>{header}{body}</table></div>"
    except Exception as e:
        return f"<div>Error generating diff: {e}</div>"


def action_diff_for_file(current_book: str, rel_path: str) -> Tuple[str, str]:
    if not current_book or not rel_path:
        return "Select a book and file.", ""
    root = Path(current_book)
    cur = root / rel_path
    bak = _backup_path_for(cur)
    if not cur.exists():
        return f"File not found: {rel_path}", ""
    if not bak.exists():
        return f"No backup found for {rel_path} (expected '{rel_path}.back').", ""
    left = _read_text(bak)
    right = _read_text(cur)
    title = f"Diff: {rel_path}.back ⟷ {rel_path}"
    return title, _diff_html(left, right, f"{rel_path}.back", rel_path)


def action_diff_latest(current_book: str) -> Tuple[str, str]:
    if not current_book:
        return "Select a book first.", ""
    rel = get_last_edited_file_for_book(current_book)
    if not rel:
        return "No recent edits to diff.", ""
    return action_diff_for_file(current_book, rel)


# ----------------------------- UI Actions ---------------------------------

def action_refresh_books() -> List[str]:
    return list_books()


def action_select_book(name: str) -> Tuple[str, str, List[str]]:
    if not name:
        return "", "", []
    p = book_path(name)
    cfg_text = ""
    cfg_path = p / "storycraftr.json"
    if not cfg_path.exists():
        alt = p / "papercraftr.json"
        cfg_path = alt if alt.exists() else cfg_path
    if cfg_path.exists():
        cfg_text = read_text_file(cfg_path)
    files = get_book_files(p)
    return str(p), cfg_text, files


def action_new_project(project_name: str, behavior_text: str, primary_language: str, openai_model: str, openai_url: str) -> Tuple[str, str]:
    if not project_name:
        return "Project name is required.", ""
    project = book_path(project_name)
    behavior_path = project / "behaviors" / "default.txt"

    # Stage behavior file
    msg = write_text_file(behavior_path, behavior_text or "")
    if msg.startswith("Error"):
        return msg, ""

    # Initialize project structure directly
    try:
        init_structure_story(
            book_path=str(project),
            license="CC BY-NC-SA",
            primary_language=primary_language or "en",
            alternate_languages=[],
            default_author="Author Name",
            genre="fantasy",
            behavior_content=behavior_text or "",
            reference_author="None",
            cli_name="storycraftr",
            openai_url=openai_url or "https://api.openai.com/v1",
            openai_model=openai_model or "gpt-4o",
        )
        return f"Initialized at {project}", "Initialized via direct API."
    except Exception as e:
        return f"Initialization error: {e}", ""


def _append_activity(current_book: str, text: str) -> str:
    if not current_book:
        return text
    try:
        act = get_last_activity_for_book(current_book)
        if act:
            return (text or "Done.") + "\n\n---\nRecent activity:\n" + act
    except Exception:
        pass
    return text


def action_outline(cmd: str, current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if not prompt:
        return "Provide a prompt."
    try:
        if cmd == "general-outline":
            return _append_activity(current_book, generate_general_outline(current_book, prompt) or "Done.")
        if cmd == "character-summary":
            return _append_activity(current_book, generate_character_summary(current_book, prompt) or "Done.")
        if cmd == "plot-points":
            return _append_activity(current_book, generate_plot_points(current_book, prompt) or "Done.")
        if cmd == "chapter-synopsis":
            return _append_activity(current_book, generate_chapter_synopsis(current_book, prompt) or "Done.")
        return f"Unknown outline command: {cmd}"
    except Exception as e:
        return f"Error: {e}"


def action_worldbuilding(cmd: str, current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if not prompt:
        return "Provide a prompt."
    try:
        if cmd == "history":
            return _append_activity(current_book, generate_history(current_book, prompt) or "Done.")
        if cmd == "geography":
            return _append_activity(current_book, generate_geography(current_book, prompt) or "Done.")
        if cmd == "culture":
            return _append_activity(current_book, generate_culture(current_book, prompt) or "Done.")
        if cmd == "technology":
            return _append_activity(current_book, generate_technology(current_book, prompt) or "Done.")
        if cmd == "magic-system":
            return _append_activity(current_book, generate_magic_system(current_book, prompt) or "Done.")
        return f"Unknown worldbuilding command: {cmd}"
    except Exception as e:
        return f"Error: {e}"


def action_chapter(chapter_number: int, current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if not prompt:
        return "Provide a prompt."
    try:
        return _append_activity(current_book, generate_chapter(current_book, int(chapter_number), prompt) or "Done.")
    except Exception as e:
        return f"Error: {e}"


def action_cover(cmd: str, current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if not prompt:
        return "Provide a prompt."
    try:
        if cmd == "cover":
            return _append_activity(current_book, generate_cover(current_book, prompt) or "Done.")
        if cmd == "back-cover":
            return _append_activity(current_book, generate_back_cover(current_book, prompt) or "Done.")
        return f"Unknown cover command: {cmd}"
    except Exception as e:
        return f"Error: {e}"


def action_publish_pdf(language: str, translate: str, current_book: str) -> str:
    if not current_book:
        return "Select a book first."
    if not language:
        return "Provide primary language (e.g., en)."
    try:
        output_pdf = to_pdf(current_book, language, translate or None)
        return f"PDF generated at: {output_pdf}"
    except SystemExit:
        return "Publishing aborted due to missing dependencies. See logs."
    except Exception as e:
        return f"Error generating PDF: {e}"


def action_iterate_check_names(current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    try:
        result = iterate_check_names(current_book)
        text = str(result) if result is not None else "Done."
        return _append_activity(current_book, text)
    except Exception as e:
        return f"Error: {e}"


def action_iterate_fix_name(current_book: str, original_name: str, new_name: str) -> str:
    if not current_book:
        return "Select a book first."
    if not original_name or not new_name:
        return "Provide both original and new names."
    try:
        fix_name_in_chapters(current_book, original_name, new_name)
        return _append_activity(current_book, "Name change completed.")
    except Exception as e:
        return f"Error: {e}"


def action_iterate_refine_motivation(current_book: str, character_name: str, story_context: str) -> str:
    if not current_book:
        return "Select a book first."
    if not character_name or not story_context:
        return "Provide character name and story context."
    try:
        refine_character_motivation(current_book, character_name, story_context)
        return _append_activity(current_book, "Motivation refined.")
    except Exception as e:
        return f"Error: {e}"


def action_iterate_strengthen_argument(current_book: str, argument: str) -> str:
    if not current_book:
        return "Select a book first."
    if not argument:
        return "Provide an argument to strengthen."
    try:
        strengthen_core_argument(current_book, argument)
        return _append_activity(current_book, "Core argument strengthened.")
    except Exception as e:
        return f"Error: {e}"


def action_iterate_insert_chapter(current_book: str, position: int, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if position is None or not prompt:
        return "Provide position and prompt."
    try:
        insert_new_chapter(current_book, int(position), prompt)
        return _append_activity(current_book, "Chapter inserted.")
    except Exception as e:
        return f"Error: {e}"


def action_iterate_add_flashback(current_book: str, position: int, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if position is None or not prompt:
        return "Provide position and prompt."
    try:
        insert_new_chapter(current_book, int(position), prompt, flashback=True)
        return _append_activity(current_book, "Flashback inserted.")
    except Exception as e:
        return f"Error: {e}"


def action_iterate_split_chapter(current_book: str, position: int, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if position is None or not prompt:
        return "Provide position and prompt."
    try:
        insert_new_chapter(current_book, int(position), prompt, split=True)
        return _append_activity(current_book, "Split inserted.")
    except Exception as e:
        return f"Error: {e}"


def action_iterate_check_consistency(current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if not prompt:
        return "Provide a prompt."
    try:
        check_consistency_across(current_book, prompt)
        return _append_activity(current_book, "Consistency check complete.")
    except Exception as e:
        return f"Error: {e}"




def action_load_file(current_book: str, rel_path: str) -> str:
    if not current_book or not rel_path:
        return ""
    target = Path(current_book) / rel_path
    # If file doesn't exist yet, open an empty buffer so user can save to create it
    if not target.exists():
        return ""
    return read_text_file(target)


def action_save_file(current_book: str, rel_path: str, content: str) -> str:
    if not current_book or not rel_path:
        return "No file selected."
    return write_text_file(Path(current_book) / rel_path, content)


def action_create_file(current_book: str, rel_path: str) -> Tuple[str, List[str]]:
    if not current_book or not rel_path:
        return "Provide a relative path.", []
    msg = write_text_file(Path(current_book) / rel_path, "")
    files = get_book_files(Path(current_book))
    return msg, files


def action_list_chapters(current_book: str) -> List[str]:
    if not current_book:
        return []
    return list_chapter_files(Path(current_book))


def action_load_chapter(current_book: str, rel_path: str) -> str:
    return action_load_file(current_book, rel_path)


def action_save_chapter(current_book: str, rel_path: str, content: str) -> str:
    return action_save_file(current_book, rel_path, content)


# Reload assistant/vector store files for the current book
def action_reload_files(current_book: str) -> str:
    if not current_book:
        return "Select a book first."
    try:
        if not load_book_config(current_book):
            return "Project not initialized or config missing."
        assistant = create_or_get_assistant(current_book)
        update_agent_files(current_book, assistant)
        return f"Agent files reloaded successfully for project: {current_book}"
    except Exception as e:
        return f"Error reloading files: {e}"


# ----------------------------- UI Layout ---------------------------------

def build_app() -> gr.Blocks:
    with gr.Blocks(title="StoryCraftr UI", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# StoryCraftr — Books, Creation Wizard, and Workspace")

        # Global state
        current_book_name = gr.Textbox(value="", visible=False)
        current_book_path = gr.Textbox(value="", visible=False)

        with gr.Tabs():
            # -------------------- Books Management Page --------------------
            with gr.Tab("Books"):
                gr.Markdown("## Manage your books\nSelect a book to work on, delete existing, or refresh the list. Use the Create tab to add a new one.")
                with gr.Row():
                    with gr.Column(scale=1):
                        books_dropdown = gr.Dropdown(choices=list_books(), label="Existing books", interactive=True, info="Select a book folder under your books directory.")
                        refresh_btn = gr.Button("Refresh list")
                        load_btn = gr.Button("Load book")
                        delete_btn = gr.Button("Delete selected book")
                        book_msg = gr.Markdown()
                    with gr.Column(scale=2):
                        gr.Markdown("### Selected Book Config (read-only)")
                        cfg_view = gr.Code(label="Configuration JSON", language="json")
                        current_book_label = gr.Markdown()

                refresh_btn.click(action_refresh_books, outputs=books_dropdown)

                def do_refresh():
                    return gr.update(choices=list_books(), value=None)

                refresh_btn.click(do_refresh, outputs=books_dropdown)

                def books_load(name: str):
                    p, cfg_text, _files = action_select_book(name)
                    return (
                        name or "",
                        p or "",
                        cfg_text or "",
                        f"**Current Book:** {p}" if p else "",
                    )

                load_btn.click(
                    books_load,
                    inputs=books_dropdown,
                    outputs=[current_book_name, current_book_path, cfg_view, current_book_label],
                )

                def books_delete(name: str):
                    msg = delete_book(name) if name else "Select a book first."
                    return msg, gr.update(choices=list_books(), value=None), "", ""

                delete_btn.click(books_delete, inputs=books_dropdown, outputs=[book_msg, books_dropdown, cfg_view, current_book_label])

            # -------------------- Create Book Wizard Page --------------------
            with gr.Tab("Create"):
                gr.Markdown("## New Book Wizard\nFollow these steps to initialize a project. You can paste behavior text or upload a file.")
                with gr.Accordion("Step 1: Project Info", open=True):
                    new_project_name = gr.Textbox(label="Project Name", info="Folder name to create under your books directory.")
                    primary_language = gr.Textbox(label="Primary Language", value="en", info="Primary language code for your book (e.g., en, es).")
                with gr.Accordion("Step 2: Behavior", open=True):
                    behavior_text = gr.Textbox(label="Behavior Content", lines=10, placeholder="Describe tone, style, themes, narrative structure, etc.", info="Guides the AI's writing style and approach.")
                    behavior_file = gr.File(label="Or upload a behavior file", file_count="single", interactive=True)
                with gr.Accordion("Step 3: Model & API", open=True):
                    openai_model = gr.Textbox(label="OpenAI Model", value="gpt-4o", info="Model identifier to use.")
                    openai_url = gr.Textbox(label="OpenAI Base URL", value="https://api.openai.com/v1", info="Base URL for an OpenAI-compatible API.")
                create_btn = gr.Button("Create Book")
                create_msg = gr.Markdown()
                create_out = gr.Markdown(label="CLI Output")

                def wizard_create(pn, bt, bf, pl, model, url):
                    bt_content = bt
                    if bf is not None:
                        try:
                            fpath = bf.name if hasattr(bf, "name") else str(bf)
                            bt_content = Path(fpath).read_text(encoding="utf-8")
                        except Exception as e:
                            return f"Error reading uploaded file: {e}", "", gr.update(), pn or "", "", ""
                    msg, out = action_new_project(pn, bt_content or "", pl, model, url)
                    # Update books and preselect
                    p, cfg_text, _files = action_select_book(pn)
                    return (
                        msg,
                        out,
                        gr.update(choices=list_books(), value=pn),
                        pn or "",
                        p or "",
                        f"**Current Book:** {p}" if p else "",
                    )

                create_btn.click(
                    wizard_create,
                    inputs=[new_project_name, behavior_text, behavior_file, primary_language, openai_model, openai_url],
                    outputs=[create_msg, create_out, books_dropdown, current_book_name, current_book_path, current_book_label],
                )

            # -------------------- Work on Book Page --------------------
            with gr.Tab("Work"):
                gr.Markdown("## Workspace\nRun commands and edit files for the currently selected book.")
                current_book_display = gr.Markdown()

                def reflect_current_book(p: str):
                    if p:
                        return f"**Current Book:** {p}"
                    return "No book selected. Go to Books or Create to select one."

                current_book_path.change(reflect_current_book, inputs=current_book_path, outputs=current_book_display)

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Chapters")
                        chapters_dropdown = gr.Dropdown(choices=[], label="Chapters", interactive=True, info="Markdown chapter files under chapters/.")
                        load_chapter_btn = gr.Button("Load Chapter")
                        save_chapter_btn = gr.Button("Save Chapter")
                        diff_chapter_btn = gr.Button("Show Chapter Diff")
                        gr.Markdown("### Files")
                        files_dropdown = gr.Dropdown(choices=[], label="Files", interactive=True, info="Common text/markdown/json/tex files in the project.")
                        load_file_btn = gr.Button("Load File")
                        save_file_btn = gr.Button("Save File")
                        diff_file_btn = gr.Button("Show File Diff")
                        sync_btn = gr.Button("Sync Assistant Files")
                        latest_diff_btn = gr.Button("Show Latest Diff")
                    with gr.Column(scale=2):
                        chapter_editor = gr.Code(label="Chapter Editor", language="markdown")
                        file_editor = gr.Code(label="Editor", language="markdown")
                        file_msg = gr.Markdown()
                        gr.Markdown("### Diff Viewer")
                        diff_title = gr.Markdown()
                        diff_view = gr.HTML()

                # When the current book changes, refresh dropdowns
                def on_book_change(p: str):
                    if not p:
                        return gr.update(choices=[], value=None), gr.update(choices=[], value=None)
                    files = get_book_files(Path(p))
                    chapters = list_chapter_files(Path(p))
                    return gr.update(choices=chapters, value=(chapters[0] if chapters else None)), gr.update(choices=files, value=(files[0] if files else None))

                current_book_path.change(on_book_change, inputs=current_book_path, outputs=[chapters_dropdown, files_dropdown])

                # Wire file/chapter editor actions
                load_chapter_btn.click(action_load_chapter, inputs=[current_book_path, chapters_dropdown], outputs=chapter_editor)
                save_chapter_btn.click(action_save_chapter, inputs=[current_book_path, chapters_dropdown, chapter_editor], outputs=file_msg)
                load_file_btn.click(action_load_file, inputs=[current_book_path, files_dropdown], outputs=file_editor)
                save_file_btn.click(action_save_file, inputs=[current_book_path, files_dropdown, file_editor], outputs=file_msg)
                sync_btn.click(action_reload_files, inputs=current_book_path, outputs=file_msg)
                diff_chapter_btn.click(action_diff_for_file, inputs=[current_book_path, chapters_dropdown], outputs=[diff_title, diff_view])
                diff_file_btn.click(action_diff_for_file, inputs=[current_book_path, files_dropdown], outputs=[diff_title, diff_view])
                latest_diff_btn.click(action_diff_latest, inputs=current_book_path, outputs=[diff_title, diff_view])

                # Command sections
                with gr.Tabs():
                    with gr.Tab("Outline"):
                        gr.Markdown("Generate high-level structure: general outline, character summaries, plot points, chapter synopsis.")
                        # Helper updater
                        def get_outline_help(cmd: str) -> str:
                            return OUTLINE_HELP.get(cmd, "")
                        with gr.Row():
                            with gr.Column():
                                outline_cmd = gr.Dropdown(choices=["general-outline", "character-summary", "plot-points", "chapter-synopsis"], value="general-outline", label="Outline Command", info="Choose which outline action to run.")
                                outline_prompt = gr.Textbox(label="Prompt", lines=4, info="Describe what you want to generate.")
                                run_outline = gr.Button("Run Outline")
                            with gr.Column():
                                outline_help = gr.Markdown(value=OUTLINE_HELP["general-outline"], label="Help")
                                outline_out = gr.Markdown(label="Output")
                        outline_cmd.change(get_outline_help, inputs=outline_cmd, outputs=outline_help)
                        def _outline_and_diff(cmd: str, book: str, pr: str):
                            msg = action_outline(cmd, book, pr)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        run_outline.click(_outline_and_diff, inputs=[outline_cmd, current_book_path, outline_prompt], outputs=[outline_out, diff_title, diff_view])

                    with gr.Tab("Worldbuilding"):
                        gr.Markdown("Create history, geography, culture, technology, magic/science system.")
                        # Helper updater
                        def get_world_help(cmd: str) -> str:
                            return WORLD_HELP.get(cmd, "")
                        with gr.Row():
                            with gr.Column():
                                world_cmd = gr.Dropdown(choices=["history", "geography", "culture", "technology", "magic-system"], value="history", label="Worldbuilding Command", info="Choose a worldbuilding area.")
                                world_prompt = gr.Textbox(label="Prompt", lines=4, info="Describe what to generate.")
                                run_world = gr.Button("Run Worldbuilding")
                            with gr.Column():
                                world_help = gr.Markdown(value=WORLD_HELP["history"], label="Help")
                                world_out = gr.Markdown(label="Output")
                        world_cmd.change(get_world_help, inputs=world_cmd, outputs=world_help)
                        def _world_and_diff(cmd: str, book: str, pr: str):
                            msg = action_worldbuilding(cmd, book, pr)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        run_world.click(_world_and_diff, inputs=[world_cmd, current_book_path, world_prompt], outputs=[world_out, diff_title, diff_view])

                    with gr.Tab("Chapters"):
                        gr.Markdown("Generate chapters and book cover texts.")
                        with gr.Row():
                            with gr.Column():
                                ch_num = gr.Number(label="Chapter Number", value=1, precision=0, info="The chapter index to generate.")
                                ch_prompt = gr.Textbox(label="Chapter Prompt", lines=4, info="Describe the content to generate for this chapter.")
                                btn_chapter = gr.Button("Generate Chapter")
                                cover_prompt = gr.Textbox(label="Cover Prompt", lines=2, info="Describe the cover text to generate.")
                                btn_cover = gr.Button("Generate Cover")
                                back_cover_prompt = gr.Textbox(label="Back Cover Prompt", lines=2, info="Describe the back-cover text to generate.")
                                btn_back_cover = gr.Button("Generate Back Cover")
                            with gr.Column():
                                chapters_help = gr.Markdown(
                                    label="Help",
                                    value=(
                                        "**Chapters**: Generate or refine chapter content.\n\n"
                                        "- `chapter N`: Writes to `chapters/chapter-N.md`. Use the prompt to specify scene goals, POV, tone, and constraints.\n"
                                        "- `cover`: Writes to `chapters/cover.md`. Provide book title, themes, and hook.\n"
                                        "- `back-cover`: Writes to `chapters/back-cover.md`. Provide a short blurb and stakes.\n\n"
                                        "Examples:```bash\n"
                                        "storycraftr chapters chapter 1 \"Open with Zevid infiltrating the tower...\"\n"
                                        "storycraftr chapters cover \"Generate a compelling jacket copy...\"\n"
                                        "storycraftr chapters back-cover \"Short, punchy blurb emphasizing stakes...\"\n"
                                        "```\n"
                                        "See `docs/getting_started.md` for end-to-end flow."
                                    ),
                                )
                                ch_out = gr.Markdown(label="Output")
                                cover_out = gr.Markdown(label="Cover Output")
                                back_cover_out = gr.Markdown(label="Back Cover Output")
                        def _chapter_and_diff(num: int, book: str, pr: str):
                            msg = action_chapter(num, book, pr)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        def _cover_and_diff(book: str, pr: str):
                            msg = action_cover("cover", book, pr)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        def _back_cover_and_diff(book: str, pr: str):
                            msg = action_cover("back-cover", book, pr)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        btn_chapter.click(_chapter_and_diff, inputs=[ch_num, current_book_path, ch_prompt], outputs=[ch_out, diff_title, diff_view])
                        btn_cover.click(_cover_and_diff, inputs=[current_book_path, cover_prompt], outputs=[cover_out, diff_title, diff_view])
                        btn_back_cover.click(_back_cover_and_diff, inputs=[current_book_path, back_cover_prompt], outputs=[back_cover_out, diff_title, diff_view])

                    with gr.Tab("Refine"):
                        gr.Markdown("Iterative refinement tools for working on existing books.")
                        with gr.Row():
                            with gr.Column():
                                gr.Markdown("#### Names")
                                names_prompt = gr.Textbox(label="Optional Prompt", lines=2, placeholder="Custom prompt for name check (optional)")
                                btn_check_names = gr.Button("Check Names Consistency")
                                orig_name = gr.Textbox(label="Original Name")
                                new_name = gr.Textbox(label="New Name")
                                btn_fix_name = gr.Button("Fix Character Name Across Chapters")
                            with gr.Column():
                                names_help = gr.Markdown(
                                    label="Help",
                                    value=(
                                        "**Names**: Check and fix character names across chapters.\n\n"
                                        "- `check-names [prompt?]`: Scans chapters for inconsistent names and suggests fixes.\n"
                                        "- `fix-name <original> <new>`: Renames across all chapters.\n\n"
                                        "Examples:```bash\n"
                                        "storycraftr iterate check-names \"Ensure naming consistency...\"\n"
                                        "storycraftr iterate fix-name Zevid Rhaedin\n"
                                        "```\n"
                                        "See `docs/iterate.md`."
                                    ),
                                )
                                refine_names_out = gr.Markdown(label="Names Output")
                        def _check_names_and_diff(book: str, pr: str):
                            msg = action_iterate_check_names(book, pr)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        def _fix_name_and_diff(book: str, on: str, nn: str):
                            msg = action_iterate_fix_name(book, on, nn)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        btn_check_names.click(_check_names_and_diff, inputs=[current_book_path, names_prompt], outputs=[refine_names_out, diff_title, diff_view])
                        btn_fix_name.click(_fix_name_and_diff, inputs=[current_book_path, orig_name, new_name], outputs=[refine_names_out, diff_title, diff_view])

                        with gr.Row():
                            with gr.Column():
                                gr.Markdown("#### Character Motivation")
                                character_name = gr.Textbox(label="Character Name")
                                story_context = gr.Textbox(label="Story Context", lines=3)
                                btn_refine_motivation = gr.Button("Refine Motivation")
                            with gr.Column():
                                motivation_help = gr.Markdown(
                                    label="Help",
                                    value=(
                                        "**Refine Motivation**: Deepen and align a character's motivations.\n\n"
                                        "- Provide the character's name and story context (conflicts, goals).\n\n"
                                        "Example:```bash\nstorycraftr iterate refine-motivation Zevid \"Clarify fear of losing control...\"\n```\n"
                                        "See `docs/iterate.md`."
                                    ),
                                )
                                motivation_out = gr.Markdown(label="Motivation Output")
                        def _refine_motivation_and_diff(book: str, cn: str, sc: str):
                            msg = action_iterate_refine_motivation(book, cn, sc)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        btn_refine_motivation.click(_refine_motivation_and_diff, inputs=[current_book_path, character_name, story_context], outputs=[motivation_out, diff_title, diff_view])

                        with gr.Row():
                            with gr.Column():
                                gr.Markdown("#### Core Argument")
                                argument = gr.Textbox(label="Argument", lines=2)
                                btn_strengthen = gr.Button("Strengthen Argument")
                            with gr.Column():
                                argument_help = gr.Markdown(
                                    label="Help",
                                    value=(
                                        "**Strengthen Argument**: Clarify and reinforce the core thesis/themes.\n\n"
                                        "- Provide a concise argument the book should consistently convey.\n\n"
                                        "Example:```bash\nstorycraftr iterate strengthen-argument \"Rebellion vs. control must remain central...\"\n```\n"
                                        "See `docs/iterate.md`."
                                    ),
                                )
                                argument_out = gr.Markdown(label="Argument Output")
                        def _strengthen_and_diff(book: str, arg: str):
                            msg = action_iterate_strengthen_argument(book, arg)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        btn_strengthen.click(_strengthen_and_diff, inputs=[current_book_path, argument], outputs=[argument_out, diff_title, diff_view])

                        with gr.Row():
                            with gr.Column():
                                gr.Markdown("#### Structure & Chapters")
                                insert_pos = gr.Number(label="Position", value=1, precision=0)
                                insert_prompt = gr.Textbox(label="Prompt", lines=3)
                                btn_insert = gr.Button("Insert Chapter")
                                btn_flashback = gr.Button("Insert Flashback Chapter")
                                btn_split = gr.Button("Split Chapter (Insert)")
                            with gr.Column():
                                structure_help = gr.Markdown(
                                    label="Help",
                                    value=(
                                        "**Structure**: Insert or split chapters and adjust numbering.\n\n"
                                        "- `insert-chapter <position> <prompt>`: Inserts before position; renumbers following chapters.\n"
                                        "- `add-flashback <position> <prompt>`: Inserts a flashback scene at position.\n"
                                        "- `split-chapter <position> <prompt>`: Splits chapter and renumbers.\n\n"
                                        "Examples:```bash\n"
                                        "storycraftr iterate insert-chapter 2 \"Bridge scene to set stakes...\"\n"
                                        "storycraftr iterate add-flashback 3 \"Reveal hidden alliance...\"\n"
                                        "storycraftr iterate split-chapter 3 \"Split into confrontation and aftermath...\"\n"
                                        "```\n"
                                        "See `docs/iterate.md`."
                                    ),
                                )
                                insert_out = gr.Markdown(label="Insert Output")
                        def _insert_and_diff(book: str, pos: int, pr: str):
                            msg = action_iterate_insert_chapter(book, pos, pr)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        def _flashback_and_diff(book: str, pos: int, pr: str):
                            msg = action_iterate_add_flashback(book, pos, pr)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        def _split_and_diff(book: str, pos: int, pr: str):
                            msg = action_iterate_split_chapter(book, pos, pr)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        btn_insert.click(_insert_and_diff, inputs=[current_book_path, insert_pos, insert_prompt], outputs=[insert_out, diff_title, diff_view])
                        btn_flashback.click(_flashback_and_diff, inputs=[current_book_path, insert_pos, insert_prompt], outputs=[insert_out, diff_title, diff_view])
                        btn_split.click(_split_and_diff, inputs=[current_book_path, insert_pos, insert_prompt], outputs=[insert_out, diff_title, diff_view])

                        with gr.Row():
                            with gr.Column():
                                gr.Markdown("#### Consistency Checks")
                                consistency_prompt = gr.Textbox(label="Prompt", lines=3, placeholder="e.g., Check plot consistency across chapters")
                                btn_consistency = gr.Button("Check Consistency")
                            with gr.Column():
                                consistency_help = gr.Markdown(
                                    label="Help",
                                    value=(
                                        "**Check Consistency**: Review cross-file consistency for arcs, names, and world rules.\n\n"
                                        "- Provide a prompt describing what to verify (arcs, motifs, timeline).\n\n"
                                        "Example:```bash\nstorycraftr iterate check-consistency \"Ensure motivations align across climax...\"\n```\n"
                                        "See `docs/iterate.md` and `docs/advanced.md` (reload-files)."
                                    ),
                                )
                                consistency_out = gr.Markdown(label="Consistency Output")
                        def _consistency_and_diff(book: str, pr: str):
                            msg = action_iterate_check_consistency(book, pr)
                            t, h = action_diff_latest(book)
                            return msg, t, h
                        btn_consistency.click(_consistency_and_diff, inputs=[current_book_path, consistency_prompt], outputs=[consistency_out, diff_title, diff_view])

                    with gr.Tab("Publish"):
                        gr.Markdown("Generate PDF (requires Pandoc + XeLaTeX in the image: set INCLUDE_TEX=true and rebuild).")
                        with gr.Row():
                            with gr.Column():
                                lang = gr.Textbox(label="Primary Language", value="en", info="Language to publish (e.g., en).")
                                translate = gr.Textbox(label="Translate (optional)", info="Optional translation language (e.g., es). Leave empty for none.")
                                btn_pdf = gr.Button("Publish PDF")
                            with gr.Column():
                                pub_help = gr.Markdown(
                                    label="Help",
                                    value=(
                                        "**Publish PDF**: Render your book to PDF via Pandoc + XeLaTeX.\n\n"
                                        "- Install Pandoc and XeLaTeX (see `docs/getting_started.md`).\n"
                                        "- Use primary language, optionally translate output language.\n\n"
                                        "Examples:```bash\n"
                                        "storycraftr publish pdf en\n"
                                        "storycraftr publish pdf en --translate es\n"
                                        "```"
                                    ),
                                )
                                pub_out = gr.Markdown(label="Publish Output")
                        btn_pdf.click(action_publish_pdf, inputs=[lang, translate, current_book_path], outputs=pub_out)

 

    return demo


if __name__ == "__main__":
    app = build_app()
    app.queue().launch(server_name="0.0.0.0", server_port=7860)
