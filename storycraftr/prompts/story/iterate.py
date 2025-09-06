# prompts/iterate.py

CHECK_NAMES_PROMPT = """
Check the full book (via retrieval) for character name inconsistencies.
Tasks:
- Identify variants, nicknames, misspellings, or inconsistent honorifics/titles for the same character.
- Resolve to a canonical form per character, respecting in-world usage and context.
Editing discipline:
- Preserve headings and chapter structure (Chapter/cover/back-cover/epilogue labels unchanged).
- Make the minimal necessary textual edits to fix inconsistencies.
"""

FIX_NAME_PROMPT = """
Replace '{original_name}' with '{new_name}' where contextually correct in this file.
Guidelines:
- Consider nicknames, diminutives, titles, and grammatical inflections; adjust to fit grammar and voice.
- Do not alter scene content beyond the necessary name substitutions.
- Preserve all headings and the existing formatting.
"""

REFINE_MOTIVATION_PROMPT = """
Refine '{character_name}' motivation using retrieval context and this guidance: {story_context}.
Ensure actions, dialogue, and internal thoughts align with a coherent arc.
Editing discipline:
- Make minimal changes that improve clarity and consistency; keep voice and pacing.
- Do not change headings or chapter numbering.
"""

STRENGTHEN_ARGUMENT_PROMPT = """
Strengthen the core argument '{argument}' in this chapter while preserving style and structure.
Ensure the theme is legible in beats, turning points, and character choices without heavy-handed exposition.
Make minimal textual edits; keep headings and numbering unchanged.
"""

INSERT_CHAPTER_PROMPT = """
Insert a new chapter at position {position} using retrieval context.
Numbering expectations:
- When a new chapter is inserted at position {position}, all subsequent chapters will be renumbered accordingly (e.g., old chapter 3 becomes 4, 4 becomes 5, etc.).
Requirements for the new chapter:
- Fit tone, pacing, and arcs between surrounding chapters.
- Begin with heading: "Chapter {position}: <Title>".
- Scene flow: setup → conflict → development → turning point → exit hook.
- Do not modify other chapters in this response.
"""

REWRITE_SURROUNDING_CHAPTERS_PROMPT = """
Refine this chapter to flow with its neighbors using retrieval context.
Keep numbering, heading format, and structure; make minimal necessary edits for continuity.
"""

INSERT_FLASHBACK_CHAPTER_PROMPT = """
Insert a flashback chapter at position {position} using retrieval context.
Numbering expectations:
- When a new chapter is inserted at position {position}, all subsequent chapters will be renumbered accordingly (e.g., old chapter 3 becomes 4, 4 becomes 5, etc.).
Requirements for the flashback chapter:
- Clarify backstory that deepens current arcs without stalling present momentum.
- Begin with heading: "Chapter {position}: <Title>".
- Anchor the flashback with a present-time frame device (opening and/or closing beat).
- Do not modify other chapters in this response.
"""

REWRITE_SURROUNDING_CHAPTERS_FOR_FLASHBACK_PROMPT = """
Refine this chapter to integrate a newly inserted flashback adjacent to it.
Maintain tone, pacing, and arc continuity with minimal edits; keep numbering and heading style.
"""

CHECK_CHAPTER_CONSISTENCY_PROMPT = """
Check this chapter for consistency with the entire book using retrieval context.
Verify: events order, character states, tone/voice, and unresolved threads.
Make minimal fixes directly in the text without altering headings or numbering.
"""

INSERT_SPLIT_CHAPTER_PROMPT = """
Split the existing chapter at position {position} into two chapters using a natural pivot.
Numbering expectations:
- Create a new chapter at position {position} containing the first half; the original chapter becomes Chapter {position+1} with the remaining half.
Requirements for the new chapter:
- Begin with heading: "Chapter {position}: <Title>".
- Include a coherent arc for the extracted first half and a clear handoff to the next chapter.
- Ensure both halves keep tone and arcs consistent.
- Generate content only for the new resulting chapters, not for the surrounding chapters.
"""

REWRITE_SURROUNDING_CHAPTERS_FOR_SPLIT_PROMPT = """
Refine this chapter to flow after a split of the previous chapter.
Maintain continuity, tone, and character states with minimal edits; headings/numbering unchanged.
Ensure transitions, references, and callbacks reflect the new boundary between the split chapters.
"""
