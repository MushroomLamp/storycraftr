import os
import secrets  # Para generar números aleatorios seguros
import yaml
import json
from typing import NamedTuple
from rich.console import Console
from rich.markdown import Markdown  # Importar soporte de Markdown de Rich
from storycraftr.prompts.permute import longer_date_formats
from storycraftr.state import debug_state  # Importar el estado de debug
from pathlib import Path
from types import SimpleNamespace

console = Console()


def generate_prompt_with_hash(original_prompt: str, date: str, book_path: str) -> str:
    """
    Generates a modified prompt by combining a random phrase from a list,
    a date, and the original prompt. Logs the prompt details in a YAML file.

    Args:
        original_prompt (str): The original prompt to be modified.
        date (str): The current date to be used in the prompt.
        book_path (str): Path to the book's directory where prompts.yaml will be saved.

    Returns:
        str: The modified prompt with the date and random phrase.
    """
    # Selecciona una frase aleatoria segura de la lista
    random_phrase = secrets.choice(longer_date_formats).format(date=date)
    modified_prompt = f"{random_phrase}\n\n{original_prompt}"

    # Define la ruta del archivo YAML
    yaml_path = Path(book_path) / "prompts.yaml"

    # Nueva entrada de log con fecha y prompt original
    log_entry = {"date": str(date), "original_prompt": original_prompt}

    # Verifica si el archivo YAML existe y carga los datos
    if yaml_path.exists():
        with yaml_path.open("r", encoding="utf-8") as file:
            existing_data = (
                yaml.safe_load(file) or []
            )  # Carga una lista vacía si está vacío
    else:
        existing_data = []

    # Añade la nueva entrada al log
    existing_data.append(log_entry)

    # Guarda los datos actualizados en el archivo YAML
    with yaml_path.open("w", encoding="utf-8") as file:
        yaml.dump(existing_data, file, default_flow_style=False)

    # Imprime el prompt modificado en Markdown si el modo debug está activado
    if debug_state.is_debug():
        console.print(Markdown(modified_prompt))

    return modified_prompt


class BookConfig(NamedTuple):
    """
    A NamedTuple representing the configuration of a book.

    Attributes:
        book_path (str): The path to the book's directory.
        book_name (str): The name of the book.
        primary_language (str): The primary language of the book.
        alternate_languages (list): A list of alternate languages.
        default_author (str): The default author of the book.
        genre (str): The genre of the book.
        license (str): The license type for the book.
        reference_author (str): A reference author for style guidance.
        keywords (str): Keywords for the paper (optional).
        cli_name (str): The name of the CLI tool used.
        openai_url (str): The URL of the OpenAI API.
        openai_model (str): The OpenAI model to use.
        multiple_answer (bool): Whether multiple answers are allowed.
    """

    book_path: str
    book_name: str
    primary_language: str
    alternate_languages: list
    default_author: str
    genre: str
    license: str
    reference_author: str
    keywords: str
    cli_name: str
    openai_url: str
    openai_model: str
    multiple_answer: bool


def load_book_config(book_path: str):
    """
    Load configuration from the book path.
    """
    if not book_path:
        console.print(
            "[red]Error: Please either:\n"
            "1. Run the command inside a StoryCraftr/PaperCraftr project directory, or\n"
            "2. Specify the project path using --book-path[/red]"
        )
        return None

    try:
        # Intentar cargar papercraftr.json primero
        config_path = Path(book_path) / "papercraftr.json"
        if not config_path.exists():
            # Si no existe, intentar storycraftr.json
            config_path = Path(book_path) / "storycraftr.json"
            if not config_path.exists():
                console.print(
                    "[red]Error: No configuration file found. Please either:\n"
                    "1. Run the command inside a StoryCraftr/PaperCraftr project directory, or\n"
                    "2. Specify the project path using --book-path[/red]"
                )
                return None

        config_data = json.loads(config_path.read_text(encoding="utf-8"))

        # Ensure required fields exist with default values
        default_config = {
            "book_name": "Untitled Paper",
            "authors": [],
            "primary_language": "en",
            "alternate_languages": [],
            "default_author": "Unknown Author",
            "genre": "research",
            "license": "CC BY",
            "reference_author": "",
            "keywords": "",
            "cli_name": "papercraftr",
            "openai_url": "https://api.openai.com/v1",
            "openai_model": "gpt-4o",
            "multiple_answer": True,
        }

        # Update default config with actual config data
        for key, value in config_data.items():
            default_config[key] = value

        return SimpleNamespace(**default_config)

    except Exception as e:
        console.print(f"[red]Error loading configuration: {str(e)}[/red]")
        return None


def file_has_more_than_three_lines(file_path: str) -> bool:
    """
    Check if a file has more than three lines.

    Args:
        file_path (str): The path to the file.

    Returns:
        bool: True if the file has more than three lines, False otherwise.
    """
    try:
        with Path(file_path).open("r", encoding="utf-8") as file:
            # Itera sobre las primeras 4 líneas y devuelve True si hay más de 3 líneas
            for i, _ in enumerate(file, start=1):
                if i > 3:
                    return True
    except FileNotFoundError:
        console.print(f"[red bold]Error:[/red bold] File not found: {file_path}")
        return False
    return False


# ---------------- Conversation persistence (per book) ----------------

def _conversation_state_path(book_path: str) -> Path:
    """
    Return the path to the conversation state file for a book.

    We persist a single default conversation id per book. This aligns with
    StoryCraftr's single-assistant-per-book design (assistant name == book folder).
    """
    return Path(book_path) / "conversations.json"


def load_conversation_id(book_path: str, agent_name: str | None = None) -> str | None:
    """
    Load the persisted conversation id for a book, if present.
    """
    try:
        path = _conversation_state_path(book_path)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        # Expect namespaced by agent name
        if isinstance(data, dict):
            if agent_name and isinstance(data.get(agent_name), str):
                return data[agent_name]
        return None
    except Exception:
        return None


def save_conversation_id(book_path: str, conversation_id: str, agent_name: str | None = None) -> None:
    """
    Persist the conversation id for a book.
    """
    try:
        path = _conversation_state_path(book_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    data = existing
            except Exception:
                data = {}
        if agent_name:
            data[str(agent_name)] = str(conversation_id)
        else:
            # If no agent name provided, do nothing to avoid ambiguous persistence
            return
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Best-effort persistence; ignore errors silently
        pass


def clear_conversation_id(book_path: str, agent_name: str | None = None) -> None:
    """
    Remove the persisted conversation id for the given agent in this book, if any.
    """
    try:
        path = _conversation_state_path(book_path)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and agent_name in data:
            del data[agent_name]
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass