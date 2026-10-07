"""Command-line messages in English or Russian.

The language follows GENE_LANG, then LC_ALL / LC_MESSAGES / LANG (ru_RU.UTF-8 → Russian).
"""
import os


def cli_language():
    for var in ("GENE_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "ru" if value.lower().startswith("ru") else "en"
    return "en"


def m(en, ru):
    """Pick the message for the current CLI language."""
    return ru if cli_language() == "ru" else en
