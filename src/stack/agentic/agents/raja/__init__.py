"""
Raja — agent shipped by creator_raja_lab.

A separate builder taught this bot chess only and registered it on Boardman.
Does not import Nero. House never plays for it.
"""
from gaming.src.stack.agentic.agents.raja.manifest import MANIFEST
from gaming.src.stack.agentic.agents.raja.mind import MIND, OPENINGS_WHITE, OPENINGS_BLACK

__all__ = ["MANIFEST", "MIND", "OPENINGS_WHITE", "OPENINGS_BLACK"]
