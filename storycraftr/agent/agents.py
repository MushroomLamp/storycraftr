import os
import glob
import time
import openai
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.progress import Progress
from storycraftr.prompts.story.core import FORMAT_OUTPUT
from storycraftr.utils.core import load_book_config, generate_prompt_with_hash
from storycraftr.utils.core import load_conversation_id, save_conversation_id
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

console = Console()


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
        "gpt-4" if config is None else getattr(config, "openai_model", "gpt-4")
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


def create_message(
    book_path: str,
    thread_id: str,
    content: str,
    assistant,
    file_path: str = None,
    progress: Progress = None,
    task_id=None,
    force_single_answer: bool = False,
) -> str:
    """
    Create a message in the thread and process it asynchronously. If config.multiple_answer is true,
    the assistant response will be requested in parts, iterating until the response is complete.

    Args:
        book_path (str): Path to the book directory.
        thread_id (str): ID of the thread where the message will be created.
        content (str): The content of the message.
        assistant (object): The assistant object with an ID.
        file_path (str, optional): The path to a file to attach as an attachment. Defaults to None.
        progress (Progress, optional): Progress object for tracking. Defaults to None.
        task_id (int, optional): Task ID for the progress bar.
        force_single_answer (bool, optional): If true, forces a single response regardless of config.multiple_answer. Defaults to False.

    Returns:
        str: The generated response text from the assistant, post-processed if multiple_answer is true.
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
            content = (
                f"{content}\n\nHere is the existing content to improve:\n{file_content}"
            )
    else:
        if should_print:
            console.print(
                f"[bold blue]Using provided prompt to generate new content...[/bold blue]"
            )

    # Add instructions for multiple answers if the flag is true and force_single_answer is false
    if config.multiple_answer and not force_single_answer:
        console.print(
            "[bold blue]Adding multi-part response generation instructions (3 parts total)...[/bold blue]"
        )
        content = (
            "Please provide the response in exactly 3 parts to avoid output token limitations. "
            "ONLY in the final (third) part, indicate 'END_OF_RESPONSE' when the response is complete. "
            "Continue providing the next part of the response when you receive the prompt 'next'.\n\n"
            + content
        )

    # Generar el prompt con hash
    prompt_with_hash = generate_prompt_with_hash(
        f"{FORMAT_OUTPUT.format(reference_author=config.reference_author, language=config.primary_language)}\n\n{content}",
        datetime.now().strftime("%B %d, %Y"),
        book_path=book_path,
    )

    try:
        if config.multiple_answer and not force_single_answer:
            console.print(
                "[bold blue]Starting multi-part response generation (3 parts total)...[/bold blue]"
            )

        if internal_progress:
            progress.start()

        done_flag = "END_OF_RESPONSE"

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
            texts = []
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
                                texts.append(c.get("text"))
                            # Older structure: {"type": "text", "text": {"value": "..."}}
                            elif c.get("type") == "text":
                                inner = c.get("text")
                                if isinstance(inner, dict) and isinstance(inner.get("value"), str):
                                    texts.append(inner.get("value"))
            return "\n".join(texts) if texts else ""

        # Compose base instruction + user input
        base_instructions = assistant.instructions if hasattr(assistant, "instructions") else ""
        vector_store_id = get_vector_store_id_by_name(assistant.name, client)

        def _create_response(input_text: str):
            tools = (
                [{"type": "file_search", "vector_store_ids": [vector_store_id]}]
                if vector_store_id
                else [{"type": "file_search"}]
            )
            kwargs = dict(
                model=assistant.model,
                input=f"System instructions:\n{base_instructions}\n\nUser:\n{input_text}",
                #temperature=0.7,
                top_p=1.0,
                tools=tools,
            )
            # Use conversation to preserve message continuity if supported
            if thread_id:
                try:
                    return client.responses.create(**kwargs, conversation={"id": thread_id})
                except TypeError:
                    try:
                        return client.responses.create(**kwargs, conversation=thread_id)
                    except TypeError:
                        return client.responses.create(**kwargs)
            return client.responses.create(**kwargs)

        # First response
        response = _create_response(prompt_with_hash)
        response_text = _extract_text(response)

        if config.multiple_answer and not force_single_answer:
            console.print("[bold green]✓ First part of the response received[/bold green]")

        # Continue for next parts if needed
        iter = 0
        while (not force_single_answer and (done_flag not in response_text) and iter < 2):
            iter += 1
            if should_print:
                console.print(f"[bold blue]Requesting part {iter + 1} of 3...[/bold blue]")

            next_prompt = "next"
            if iter == 2:
                next_prompt = "THIS IS THE FINAL PART. PLEASE COMPLETE YOUR RESPONSE AND END WITH 'END_OF_RESPONSE'."
                console.print("[bold yellow]⚠ This is the final part. The response should be completed and include END_OF_RESPONSE.[/bold yellow]")

            conversation = (
                f"{prompt_with_hash}\n\nAssistant so far:\n{response_text}\n\n{next_prompt}"
            )
            response = _create_response(conversation)
            new_response = _extract_text(response)

            if config.multiple_answer and not force_single_answer:
                console.print(f"[bold green]✓ Part {iter + 1} of 3 received[/bold green]")

            response_text += "\n" + new_response

        if internal_progress:
            progress.stop()

        if done_flag in response_text:
            response_text = response_text.replace(done_flag, "")
            if config.multiple_answer and not force_single_answer:
                console.print(
                    "[bold green]✓ END_OF_RESPONSE detected - Response completed successfully with all 3 parts[/bold green]"
                )

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


def delete_file(vector_stores_api, vector_store_id, file_id):
    """Delete a single file from the vector store."""
    try:
        vector_stores_api.files.delete(vector_store_id=vector_store_id, file_id=file_id)
    except Exception as e:
        console.print(f"[bold red]Error deleting file {file_id}: {str(e)}[/bold red]")


def delete_files_in_parallel(vector_stores_api, vector_store_id, files):
    """Delete multiple files from the vector store in parallel using ThreadPoolExecutor."""
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(delete_file, vector_stores_api, vector_store_id, file.id)
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
        files = vector_stores_api.files.list(vector_store_id=vector_store_id)

        # Eliminar archivos en paralelo
        if files.data:
            console.print(
                f"[bold blue]Deleting {len(files.data)} old files...[/bold blue]"
            )
            delete_files_in_parallel(vector_stores_api, vector_store_id, files)

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
