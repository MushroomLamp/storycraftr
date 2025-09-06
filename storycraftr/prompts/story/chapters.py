# prompts/chapters.py

CHAPTER_PROMPT_NEW = """
Write one complete, engaging chapter in {language} based on: {prompt}.
Use the retrieval system to stay consistent with the existing world, plot, and character arcs.
Requirements:
- Output a single chapter only, not an overarching story arc.
- Begin with a single line chapter heading in the format: "Chapter X: <Title>" (no extra subtitles).
- Maintain consistent tone and voice with prior chapters.
- Keep pacing balanced: scene-setting, conflict, turning point, and a hook for the next chapter.
"""


CHAPTER_PROMPT_REFINE = """
Refine the existing chapter using retrieval context and this guidance: {prompt}.
Improve narrative flow, character depth, and pacing with minimal necessary changes.
Requirements:
- Do not change the chapter number or heading style; keep: "Chapter X: <Title>".
- Preserve existing section order and continuity unless a change is essential.
- Fix inconsistencies with prior chapters via retrieval context.
"""


COVER_PROMPT = """
Create the cover page in markdown for '{title}' by {author}.
Requirements:
- Output only the cover content in markdown (no fences, no commentary).
- Keep it minimal: title and author only; no additional text.
- If prior cover content exists, improve typography/spacing minimally without changing the content intent.
Source guidance: {prompt}
"""


BACK_COVER_PROMPT = """
Write the back-cover synopsis for '{title}' by {author} in markdown.
Include:
- A compelling 1–2 paragraph synopsis (no spoilers, strong hook).
- A single line for genre: {genre}.
- One line listing available languages: {alternate_languages}.
- A license note that explicitly names the license: {license}, with a concise professional description.
Output only the back-cover content in markdown. If improving prior text, keep changes minimal.
Source guidance: {prompt}
"""


EPILOGUE_PROMPT_NEW = """
Write a complete epilogue in {language} using retrieval context and this guidance: {prompt}.
Tie up loose ends and provide resonance with the main themes and character arcs.
Requirements:
- Output a single epilogue chapter only.
- Begin with a heading: "Epilogue" (no numbering, no subtitle).
- Maintain tone and continuity with the final chapters.
"""


EPILOGUE_PROMPT_REFINE = """
Refine the epilogue using retrieval context and this guidance: {prompt}.
Improve flow, thematic closure, and emotional cadence with minimal necessary edits.
Requirements:
- Keep the heading exactly: "Epilogue".
- Preserve existing structure unless a change is essential.
- Ensure consistency with the preceding chapters.
"""
