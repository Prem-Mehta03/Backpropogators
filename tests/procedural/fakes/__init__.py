"""Test doubles for the other two layers: contract-valid fixtures, no real storage or sensors.

They exist so the procedural tests run on a clean clone without the other layers' code.
They are not stubs of the real API and are never imported by production code except as the
offline fallback in scripts/tool_wiring.py.
"""
