"""
Nero — agent shipped by creator_nero_forge.

A separate builder taught this bot chess only and registered it on Boardman.
Does not import Raja. House never plays for it.
"""
from gaming.src.stack.agentic.agents.nero.manifest import MANIFEST
from gaming.src.stack.agentic.agents.nero.mind import MIND, OPENINGS_WHITE, OPENINGS_BLACK

__all__ = ["MANIFEST", "MIND", "OPENINGS_WHITE", "OPENINGS_BLACK"]
