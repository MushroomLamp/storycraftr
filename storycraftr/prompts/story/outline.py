GENERAL_OUTLINE_PROMPT_NEW = """
Create a retrieval-aware general outline for the book {book_name} in {language} based on this guidance: {prompt}.
Requirements:
- Reflect existing canon from retrieval (characters, tone, setting, constraints).
- Structure as markdown with clear top-level sections:
  - Premise
  - Themes
  - Setting
  - Protagonist and Antagonist (brief profiles)
  - Acts overview or book structure
- Keep it concise and actionable; avoid prose scenes.
"""

GENERAL_OUTLINE_PROMPT_REFINE = """
Refine the general outline using retrieval and this guidance: {prompt}.
Improve clarity, cohesion, and beat logic with minimal necessary edits.
Requirements:
- Preserve existing section headers; adjust content under them for precision and consistency.
- Ensure cross-references (themes ↔ beats, character arcs ↔ acts) are coherent.
"""

CHARACTER_SUMMARY_PROMPT_NEW = """
Create a character summary for {book_name} in {language} based on this guidance: {prompt}.
Use retrieval to ensure names, roles, and facts match existing canon.
Structure (markdown list):
- Main Characters: name, role, core desire, flaw, arc summary, relationships.
- Secondary Characters: name, role, utility, relationships.
Keep entries terse and consistent.
"""

CHARACTER_SUMMARY_PROMPT_REFINE = """
Refine the character summary using retrieval and this guidance: {prompt}.
Clarify motivations, refine arcs, and fix inconsistencies with minimal necessary edits.
Keep the same sectioning and character order unless a change is essential.
"""

PLOT_POINTS_PROMPT_NEW = """
Create the main plot points for {book_name} in {language} based on this guidance: {prompt}.
Use retrieval to align with canon.
Structure:
- Inciting Incident
- First Plot Point
- Midpoint Shift
- Second Plot Point
- Climax
- Resolution
Each point: 1–2 sentences, concrete and testable.
"""

PLOT_POINTS_PROMPT_REFINE = """
Refine the plot points using retrieval and this guidance: {prompt}.
Tighten causality and stakes; ensure progression is logical and escalatory.
Keep headings the same; update content minimally for clarity and consistency.
"""

CHAPTER_SYNOPSIS_PROMPT_NEW = """
Create a chapter-by-chapter synopsis for {book_name} in {language} based on this guidance: {prompt}.
Use retrieval for consistency with outline, characters, and plot points.
Structure:
- For N chapters (choose a reasonable N consistent with outline), list: "Chapter X: Title — 2–4 sentence synopsis".
- Ensure each chapter advances arcs and plot points; include turning points where relevant.
"""

CHAPTER_SYNOPSIS_PROMPT_REFINE = """
Refine the chapter-by-chapter synopsis using retrieval and this guidance: {prompt}.
Clarify pivotal moments, tighten tension, and align with plot points and arcs.
Preserve chapter numbering and titles; make minimal necessary changes to each synopsis.
"""
