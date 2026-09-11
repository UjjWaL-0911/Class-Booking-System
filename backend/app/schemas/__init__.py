"""Pydantic request and response models.

Kept separate from the ORM models so the wire format can change without touching
persistence, and so a column can exist without automatically being exposed.
"""
