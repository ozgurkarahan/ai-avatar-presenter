"""Operator maintenance commands that run inside the app container.

They reuse the routers' and services' own code paths with the app's managed
identity (no HTTP, no sign-in). Run from the backend directory (``/app`` in the
image), e.g. ``python -m maintenance.content inventory``.
"""
