"""
The agent layer.

This package is the only one allowed to import a model client. The engine, the
data layer and the retrieval layer stay free of one (ADR-001), which is what
makes their answers reproducible without a key.

The division it enforces: the model chooses *which question is being asked* and
*which provision to read*. It never computes a figure, asserts a rule, or picks
a number out of prose.
"""
