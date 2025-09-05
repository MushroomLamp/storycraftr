import os
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple

import gradio as gr
from rich.console import Console

 

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
            shutil.rmtree(target)
            return f"Deleted book: {book_name}"
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

    args = [
        "init",
        str(project),
        "--primary-language",
        primary_language or "en",
        "--behavior",
        str(behavior_path),
        "--openai-model",
        openai_model or "gpt-4o",
        "--openai-url",
        openai_url or "https://api.openai.com/v1",
    ]
    out, code = run_cli(args)
    if code == 0:
        return f"Initialized at {project}", out
    return out, ""


def action_outline(cmd: str, current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if not prompt:
        return "Provide a prompt."
    args = ["outline", cmd, "--book-path", current_book, "--", prompt]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_worldbuilding(cmd: str, current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if not prompt:
        return "Provide a prompt."
    args = ["worldbuilding", cmd, "--book-path", current_book, "--", prompt]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_chapter(chapter_number: int, current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if not prompt:
        return "Provide a prompt."
    args = [
        "chapters",
        "chapter",
        "--book-path",
        current_book,
        "--",
        str(int(chapter_number)),
        prompt,
    ]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_cover(cmd: str, current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if not prompt:
        return "Provide a prompt."
    args = ["chapters", cmd, "--book-path", current_book, "--", prompt]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_publish_pdf(language: str, translate: str, current_book: str) -> str:
    if not current_book:
        return "Select a book first."
    if not language:
        return "Provide primary language (e.g., en)."
    args = ["publish", "pdf", language]
    if translate:
        args.extend(["--translate", translate])
    args.extend(["--book-path", current_book])
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_iterate_check_names(current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    args = ["iterate", "check-names", "--book-path", current_book]
    if prompt:
        args.append(prompt)
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_iterate_fix_name(current_book: str, original_name: str, new_name: str) -> str:
    if not current_book:
        return "Select a book first."
    if not original_name or not new_name:
        return "Provide both original and new names."
    args = [
        "iterate",
        "fix-name",
        "--book-path",
        current_book,
        "--",
        original_name,
        new_name,
    ]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_iterate_refine_motivation(current_book: str, character_name: str, story_context: str) -> str:
    if not current_book:
        return "Select a book first."
    if not character_name or not story_context:
        return "Provide character name and story context."
    args = [
        "iterate",
        "refine-motivation",
        "--book-path",
        current_book,
        "--",
        character_name,
        story_context,
    ]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_iterate_strengthen_argument(current_book: str, argument: str) -> str:
    if not current_book:
        return "Select a book first."
    if not argument:
        return "Provide an argument to strengthen."
    args = [
        "iterate",
        "strengthen-argument",
        "--book-path",
        current_book,
        "--",
        argument,
    ]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_iterate_insert_chapter(current_book: str, position: int, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if position is None or not prompt:
        return "Provide position and prompt."
    args = [
        "iterate",
        "insert-chapter",
        "--book-path",
        current_book,
        "--",
        str(int(position)),
        prompt,
    ]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_iterate_add_flashback(current_book: str, position: int, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if position is None or not prompt:
        return "Provide position and prompt."
    args = [
        "iterate",
        "add-flashback",
        "--book-path",
        current_book,
        "--",
        str(int(position)),
        prompt,
    ]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_iterate_split_chapter(current_book: str, position: int, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if position is None or not prompt:
        return "Provide position and prompt."
    args = [
        "iterate",
        "split-chapter",
        "--book-path",
        current_book,
        "--",
        str(int(position)),
        prompt,
    ]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."


def action_iterate_check_consistency(current_book: str, prompt: str) -> str:
    if not current_book:
        return "Select a book first."
    if not prompt:
        return "Provide a prompt."
    args = [
        "iterate",
        "check-consistency",
        "--book-path",
        current_book,
        "--",
        prompt,
    ]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Done."




def action_load_file(current_book: str, rel_path: str) -> str:
    if not current_book or not rel_path:
        return ""
    return read_text_file(Path(current_book) / rel_path)


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
    args = ["reload-files", "--book-path", current_book]
    out, _ = run_cli(args, cwd=current_book)
    return out or "Synced."


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
                        gr.Markdown("### Files")
                        files_dropdown = gr.Dropdown(choices=[], label="Files", interactive=True, info="Common text/markdown/json/tex files in the project.")
                        load_file_btn = gr.Button("Load File")
                        save_file_btn = gr.Button("Save File")
                        sync_btn = gr.Button("Sync Assistant Files")
                    with gr.Column(scale=2):
                        chapter_editor = gr.Code(label="Chapter Editor", language="markdown")
                        file_editor = gr.Code(label="Editor", language="markdown")
                        file_msg = gr.Markdown()

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
                        run_outline.click(action_outline, inputs=[outline_cmd, current_book_path, outline_prompt], outputs=outline_out)

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
                        run_world.click(action_worldbuilding, inputs=[world_cmd, current_book_path, world_prompt], outputs=world_out)

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
                        btn_chapter.click(action_chapter, inputs=[ch_num, current_book_path, ch_prompt], outputs=ch_out)
                        btn_cover.click(lambda pth, pr: action_cover("cover", pth, pr), inputs=[current_book_path, cover_prompt], outputs=cover_out)
                        btn_back_cover.click(lambda pth, pr: action_cover("back-cover", pth, pr), inputs=[current_book_path, back_cover_prompt], outputs=back_cover_out)

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
                        btn_check_names.click(action_iterate_check_names, inputs=[current_book_path, names_prompt], outputs=refine_names_out)
                        btn_fix_name.click(action_iterate_fix_name, inputs=[current_book_path, orig_name, new_name], outputs=refine_names_out)

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
                        btn_refine_motivation.click(action_iterate_refine_motivation, inputs=[current_book_path, character_name, story_context], outputs=motivation_out)

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
                        btn_strengthen.click(action_iterate_strengthen_argument, inputs=[current_book_path, argument], outputs=argument_out)

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
                        btn_insert.click(action_iterate_insert_chapter, inputs=[current_book_path, insert_pos, insert_prompt], outputs=insert_out)
                        btn_flashback.click(action_iterate_add_flashback, inputs=[current_book_path, insert_pos, insert_prompt], outputs=insert_out)
                        btn_split.click(action_iterate_split_chapter, inputs=[current_book_path, insert_pos, insert_prompt], outputs=insert_out)

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
                        btn_consistency.click(action_iterate_check_consistency, inputs=[current_book_path, consistency_prompt], outputs=consistency_out)

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
