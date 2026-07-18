"""Vercel entrypoint for the browser-facing FastAPI application."""

from ceo_voice.api.app import app

__all__ = ["app"]
