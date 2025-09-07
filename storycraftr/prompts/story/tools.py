from typing import Any, Dict, List


# Text that instructs the model how to use the file editing tools.
# Kept as a template so callers can inject the target relative path.
TOOL_USAGE_GUIDANCE_TEMPLATE: str = (
    "You can modify existing files using tools. When editing an existing file, prefer making surgical edits via fs_read_text and fs_apply_text_edits instead of outputting the entire file.\n"
    "Target file (relative to book): {rel_path}. Steps: 1) fs_read_text to get current text (only if it hasnt been provided already), 2) decide minimal changes, 3) fs_apply_text_edits with precise edits (replace_text, replace_between, insert_before/insert_after)."
)


def tool_usage_guidance_for_file(rel_path: str) -> str:
    """Format the guidance text for a specific relative file path."""
    return TOOL_USAGE_GUIDANCE_TEMPLATE.format(rel_path=rel_path)


def surgical_tools_schema() -> List[Dict[str, Any]]:
    """Return the schema definitions for the file-editing tools exposed to the model."""
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
                        "description": "Relative path within the book (e.g., chapters/chapter-1.md).",
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
                                        "occurrence": {"type": "integer", "minimum": 1},
                                    },
                                    "required": ["type", "find", "replace"],
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
                                        "normalize_quotes": {"type": "boolean", "default": True},
                                    },
                                    "required": ["type", "start_marker", "end_marker", "replacement"],
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
                                        "normalize_quotes": {"type": "boolean", "default": True},
                                    },
                                    "required": ["type", "anchor", "insert"],
                                },
                            ],
                        },
                    },
                },
                "required": ["path", "edits"],
            },
        },
    ]


