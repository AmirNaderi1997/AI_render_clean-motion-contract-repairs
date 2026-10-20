"""Creative Engine: the layer that decides *what video to make and how*, above the render engines.

Pipeline (each step is a real model call, validated, never fabricated):

    understand  → ContentBrief   (what is this, for whom, what must stay true)
    ideate      → 3 Concepts     (genuinely different angles, not rewordings)
    critique    → pick + improve (a harsh second pass scored against a rubric)
    plan        → CreativePlan   (director notes the existing engines follow)

The engines stay the executors. Every step can fail (timeouts, rate limits); callers treat
`CreativeUnavailable` as "use the standard pipeline", so this layer can improve a result but
can never be the reason a job dies.
"""
from .schemas import Concept, ContentBrief, CreativePlan, Critique, CreativeUnavailable
from .director import direct_talk, direct_product, direct_idea, enabled
from . import revise

__all__ = ["Concept", "ContentBrief", "CreativePlan", "Critique", "CreativeUnavailable",
           "direct_talk", "direct_product", "direct_idea", "enabled", "revise"]
