"""Site settings: `site.json` next to `family_tree.json`.

Every key is optional except `title`; see docs/configuration.md for the full list.
"""
import json
from pathlib import Path

# Interface languages shipped with the engine. The interface source text is Russian;
# other languages are dictionaries in gene_archive/engine/i18n/<lang>.json.
UI_LANGUAGES = {
    "ru": {"name": "Русский", "locale": "ru-RU", "plural": "ru"},
    "en": {"name": "English", "locale": "en-GB", "plural": "one_other"},
    "ro": {"name": "Română", "locale": "ro-RO", "plural": "ro"},
}

DEFAULTS = {
    "title": "Family archive",
    "short_title": None,           # header brand; defaults to title
    "description": "",
    "base_url": "",                # https://example.org/family/ — enables sitemap, canonical links, hreflang
    "languages": ["en"],           # first = main language at the site root, others in /<lang>/
    "content_language": None,      # language of your texts; defaults to the first language
    "root_person": None,           # defaults to root_person_id in family_tree.json
    "start_person": None,          # who is in the centre when the tree opens
    "quick_focus": [],             # [{"label": "Mother's side", "person": "I12"}] buttons above the tree
    "branches": [],                # [{"id", "title", "focus", "about"}]
    "questions": [],               # [{"person": "I4", "text": "..."}] questions to relatives
    "story": {},                   # timeline / places / branch_tags / branch_names / branch_colors for the Story page
    "surname_variants": {},        # {"Novák": "Novak"} spellings merged into one surname
    "privacy": {"hide_living": True, "living_years": 100},
    "comments": False,             # true when the comments server (gene serve / Docker) is used
    "contact": None,               # {"email": "...", "label": "Write to us"} shown in the header
    "links": [],                   # [{"label": "...", "href": "..."}] extra items in the "More" menu
    "head_html": "",               # extra HTML for <head> of every page (analytics, verification meta tags)
    "strict_translations": False,  # fail the build when a content string has no translation
    "min_surname_page": 3,         # surname pages for surnames with at least N people
    "gedcom_version": "5.5.1",     # family_tree.ged on the site: "5.5.1" (read by most programs) or "7.0"
}


class ConfigError(ValueError):
    pass


def load(site_dir):
    """Read site.json (if present) and fill defaults. Returns a plain dict."""
    site_dir = Path(site_dir)
    path = site_dir / "site.json"
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(raw, dict):
        raise ConfigError("site.json must contain a JSON object")
    unknown = sorted(set(raw) - set(DEFAULTS) - {"$schema", "_comment"})
    if unknown:
        raise ConfigError("site.json: unknown keys " + ", ".join(unknown) + " (see docs/configuration.md)")
    cfg = json.loads(json.dumps(DEFAULTS))
    for k, v in raw.items():
        if k == "privacy" and isinstance(v, dict):
            cfg["privacy"].update(v)
        elif not k.startswith(("$", "_")):
            cfg[k] = v
    langs = cfg["languages"]
    if isinstance(langs, str):
        langs = cfg["languages"] = [langs]
    if not langs or not all(isinstance(x, str) for x in langs):
        raise ConfigError("site.json: languages must be a list such as [\"en\", \"ru\"]")
    bad = [x for x in langs if x not in UI_LANGUAGES]
    if bad:
        raise ConfigError(f"site.json: no interface translation for {bad}; available: {sorted(UI_LANGUAGES)}")
    if len(set(langs)) != len(langs):
        raise ConfigError("site.json: languages repeat")
    if cfg["gedcom_version"] not in ("5.5.1", "7.0"):
        raise ConfigError('site.json: gedcom_version must be "5.5.1" or "7.0"')
    cfg["content_language"] = cfg["content_language"] or langs[0]
    cfg["short_title"] = cfg["short_title"] or cfg["title"]
    if cfg["base_url"] and not cfg["base_url"].endswith("/"):
        cfg["base_url"] += "/"
    if cfg["base_url"] and not cfg["base_url"].startswith(("http://", "https://")):
        raise ConfigError("site.json: base_url must start with https:// (or be empty)")
    return cfg


def public(cfg):
    """The part of the settings the browser needs (goes into data.json as `site`)."""
    keys = ("title", "short_title", "base_url", "quick_focus", "story", "surname_variants", "comments")
    return {k: cfg[k] for k in keys}
