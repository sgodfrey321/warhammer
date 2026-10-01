"""Monte Carlo dice-roll simulator for 40k (2026 edition) attack sequences.

Deliberately walled off from the rest of the app: this is the first real "rules
engine" bit of code in a codebase that is otherwise bookkeeping. Nothing outside
this package (and its router) should import from it, and it imports nothing from
the rest of `app` except stdlib/pydantic-flavoured plain data.

v1 scope: one weapon profile vs one defender unit, full attack sequence (attacks
-> hits -> wounds -> saves -> damage -> allocation), run N times to build a
probability distribution of damage dealt and models slain. See montecarlo.py for
the entry point used by the /simulate endpoint.
"""

from __future__ import annotations
