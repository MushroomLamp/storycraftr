# prompts/worldbuilding.py

GEOGRAPHY_PROMPT_NEW = """
Create a retrieval-aware geography brief in {language} based on: {prompt}.
Structure (markdown headings/lists):
- Regions and Realms (names, defining traits)
- Biomes and Climate (seasonality, extremes)
- Key Locations (capitals, landmarks, natural wonders)
- Travel and Trade (routes, chokepoints, hazards)
- Resources and Pressures (scarcity, abundance, environmental issues)
- Optional: Map Notes (labels and relationships to aid cartography)
"""

GEOGRAPHY_PROMPT_REFINE = """
Refine the geography brief using retrieval and this guidance: {prompt}.
Make minimal necessary edits; preserve headings and ordering unless change is essential.
Ensure consistency with history, culture, and technology documents.
"""

HISTORY_PROMPT_NEW = """
Create a retrieval-aware history overview in {language} based on: {prompt}.
Structure:
- Eras and Timeline (bulleted eras with dates/periods)
- Founding Myths vs Attested History (where accounts diverge)
- Major Conflicts and Outcomes (winners/losers, consequences)
- Cultural/Technological Shifts (what changed and why)
- Present Status Quo (fault lines, tensions)
Keep entries concise and factual; avoid scene prose.
"""

HISTORY_PROMPT_REFINE = """
Refine the history overview using retrieval and this guidance: {prompt}.
Tighten causality and reconcile contradictions with minimal necessary edits.
Preserve section headings and timeline order.
"""

CULTURE_PROMPT_NEW = """
Create a retrieval-aware culture profile in {language} based on: {prompt}.
Structure:
- Social Structure and Norms (class, gender, kinship, etiquette)
- Languages and Dialects (who speaks what, loanwords)
- Religion and Rituals (beliefs, institutions, taboos)
- Arts, Cuisine, and Dress (aesthetic principles, signature elements)
- Law, Customs, and Holidays (legal norms, rites, festivals)
- Intercultural Relations (stereotypes, alliances, frictions)
"""

CULTURE_PROMPT_REFINE = """
Refine the culture profile using retrieval and this guidance: {prompt}.
Ensure internal consistency and alignment with geography/history; edit minimally.
Preserve headings and order unless essential.
"""

MAGIC_SYSTEM_PROMPT_NEW = """
Design a retrieval-aware magic/science system in {language} based on: {prompt}.
Structure:
- Source and Principles (where power comes from; first principles)
- Capabilities and Techniques (what can be done; common methods)
- Costs, Limits, and Failure Modes (tradeoffs, exhaustion, corruption)
- Institutions and Practitioners (guilds, orders, training)
- Societal Impact (economy, warfare, culture, law)
- Taboos, Risks, and Known Artifacts/Spells (danger and lore)
"""

MAGIC_SYSTEM_PROMPT_REFINE = """
Refine the magic/science system using retrieval and this guidance: {prompt}.
Tighten mechanics, limits, and consequences; keep edits minimal.
Preserve headings/order; ensure cross-consistency with culture/history/technology.
"""

TECHNOLOGY_PROMPT_NEW = """
Create a retrieval-aware technology profile in {language} based on: {prompt}.
Structure:
- Overall Tech Level (comparative baseline)
- Energy and Materials (sources, constraints)
- Communication and Transportation (speed, reach)
- Medicine and Agriculture (capabilities, limits)
- Military and Security (weapons, defenses, doctrine)
- Constraints and Tradeoffs (what is hard/impossible and why)
"""

TECHNOLOGY_PROMPT_REFINE = """
Refine the technology profile using retrieval and this guidance: {prompt}.
Ensure feasibility and coherence with geography, culture, and magic/science; edit minimally.
Preserve headings/order.
"""
