"""
Match-Slice — AFM demo manager agent.

Football managers only: owns a club, sets lineups and tactics.
Does not import other silos. House never plays for it. Not a chess agent.
"""
from gaming.src.stack.agentic.agents.matchslice.manifest import MANIFEST
from gaming.src.stack.agentic.agents.matchslice.mind import MIND

__all__ = ["MANIFEST", "MIND"]