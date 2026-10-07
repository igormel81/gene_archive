"""`gene build <site>`: family_tree.json + site.json + sources/ + content/ → a static site.

The result (default <site>/_site) can be published on any static hosting (GitHub Pages,
Netlify, an nginx folder) or served together with comments by `gene serve`.
"""
import hashlib
import html
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

from . import config, discovery, ged_export, localize, privacy
from .messages import m
from .validate import validate

ENGINE = Path(__file__).resolve().parent / "engine"


class BuildError(Exception):
    pass


def sha(data, n=10):
    return hashlib.sha1(data if isinstance(data, bytes) else data.encode()).hexdigest()[:n]


# --- images -------------------------------------------------------------------------------------
def make_thumb(src, dest, size, cache, transpose=True, **save):
    """A JPEG preview; cached in <site>/.cache/thumbs by file content, so only new photos are resized.
    Without Pillow the original file is used as its own preview."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        shutil.copy2(src, dest.with_suffix(Path(src).suffix))
        return dest.with_suffix(Path(src).suffix)
    cache.mkdir(parents=True, exist_ok=True)
    key = sha(Path(src).read_bytes() + repr((size, transpose, sorted(save.items()))).encode(), 20)
    out = cache / (key + ".jpg")
    if not out.exists():
        with Image.open(src) as im:
            if transpose:
                im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            im.thumbnail((size, size))
            tmp = out.with_suffix(".tmp")
            im.save(tmp, "JPEG", **save)
            tmp.replace(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, dest)
    return dest


def pdf_preview(pdf, page, cache):
    """An image of one PDF page (needs pdftoppm from poppler-utils); None when unavailable."""
    cache.mkdir(parents=True, exist_ok=True)
    key = sha(Path(pdf).read_bytes(), 16) + f"-p{page}"
    out = cache / (key + ".jpg")
    if not out.exists():
        try:
            subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile", "-jpeg", "-jpegopt", "quality=85",
                            "-scale-to", "900", str(pdf), str(cache / key)], check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError):
            return None
    return out


# --- story place tags -----------------------------------------------------------------------------
def tag_story_places(text, patterns):
    """Marks story blocks with the numbers of the places they mention: data-pl="0,3".

    Translated editions keep these marks, so the "By place" filter works in every language."""
    if not patterns:
        return text
    places = [re.compile(rx, re.I) for _, rx in patterns]
    line_start = [0]
    for ln in text.split("\n"):
        line_start.append(line_start[-1] + len(ln) + 1)

    class Blocks(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack, self.open, self.found = [], None, []

        def handle_starttag(self, tag, attrs):
            parent = self.stack[-1] if self.stack else None
            grand = self.stack[-2] if len(self.stack) > 1 else None
            if tag in ("br", "img", "hr", "meta", "link", "input", "source", "wbr"):
                return
            is_block = self.open is None and (
                (tag in ("p", "figure") and parent and parent[0] == "section") or
                (tag == "li" and parent and parent[0] == "ul" and grand and grand[0] == "section"))
            self.stack.append((tag, dict(attrs)))
            if is_block:
                line, col = self.getpos()
                self.open = {"depth": len(self.stack), "at": line_start[line - 1] + col, "tag": tag, "text": []}

        def handle_endtag(self, tag):
            while self.stack:
                t, _ = self.stack.pop()
                if self.open and len(self.stack) < self.open["depth"]:
                    self.found.append(self.open); self.open = None
                if t == tag:
                    break

        def handle_data(self, data):
            if self.open:
                self.open["text"].append(data)

    parser = Blocks()
    parser.feed(text)
    parser.close()
    for b in sorted(parser.found, key=lambda b: -b["at"]):
        hits = [str(i) for i, rx in enumerate(places) if rx.search("".join(b["text"]))]
        if hits:
            pos = b["at"] + 1 + len(b["tag"])
            text = text[:pos] + ' data-pl="' + ",".join(hits) + '"' + text[pos:]
    return text


# --- template -----------------------------------------------------------------------------------
def fill_index(template, cfg, has_story, has_news, has_help):
    esc = lambda s: html.escape(str(s), quote=True)
    contact = ""
    c = cfg.get("contact") or {}
    if c.get("email"):
        label = c.get("label") or "Написать нам"
        contact = (f'\n    <a class="mail-link" href="mailto:{esc(c["email"])}" title="{esc(label)}" aria-label="{esc(label)}">'
                   '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" '
                   'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5.5" width="18" height="13" rx="2">'
                   '</rect><path d="m3.5 7 8.5 6 8.5-6"></path></svg></a>')
    more = []
    if has_news:
        more.append('<a href="news.html">Что нового</a>')
    if has_help:
        more.append('<a href="help.html">Как пользоваться</a>')
    more.append('<a href="people/">Указатель людей</a>')
    for link in cfg.get("links") or []:
        more.append(f'<a href="{esc(link["href"])}">{esc(link["label"])}</a>')
    if c.get("email"):
        more.append(f'<a class="more-mail" href="mailto:{esc(c["email"])}">{esc(c.get("label") or "Написать нам")}<small>{esc(c["email"])}</small></a>')
    more.append('<a class="more-engine" href="https://github.com/igormel81/gene_archive" rel="noopener">gene-archive</a>')
    prefetch = ("<!--gene:root-->\nwindow.genePrefetch = { data: fetch('data.json', { credentials: 'same-origin' })"
                + (", comments: fetch(window.GENE_ROOT + 'api/comments', { credentials: 'same-origin' })" if cfg["comments"] else "")
                + " };")
    values = {
        "lang": "ru", "title": esc(cfg["title"]), "description": esc(cfg["description"]), "brand": esc(cfg["short_title"]),
        "prefetch": prefetch, "contact": contact, "more_links": "\n        ".join(more),
        "news_tab": '\n    <a role="tab" class="tab tab-news" href="news.html">Что нового</a>' if has_news else "",
        "story_tab": '<button role="tab" data-view="story">История</button>' if has_story else "",
        "scripts": '<!--gene:scripts-->\n<script src="vendor/leaflet/leaflet.js"></script>',
    }
    out = re.sub(r"\{\{(\w+)\}\}", lambda mm: values[mm[1]], template)
    if cfg.get("head_html"):
        out = out.replace("</head>", cfg["head_html"] + "\n</head>", 1)
    return out


# --- main ---------------------------------------------------------------------------------------
def load_site(site_dir):
    site_dir = Path(site_dir)
    tree = site_dir / "family_tree.json"
    if not tree.exists():
        raise BuildError(m(f"{tree} not found (start with `gene init` or `gene import tree.ged`)",
                           f"нет файла {tree} (начните с `gene init` или `gene import tree.ged`)"))
    cfg = config.load(site_dir)
    data = json.loads(tree.read_text(encoding="utf-8"))
    for p in data.get("people", []):
        if "relation" not in p and "relation_to_igor" in p:   # older name of the field
            p["relation"] = p.pop("relation_to_igor")
    return cfg, data


def public_data(cfg, raw):
    """Data as published: hidden documents removed, living people reduced to their names."""
    data = privacy.without_hidden(raw)
    root = cfg["root_person"] or data["root_person_id"]
    living = set()
    if cfg["privacy"].get("hide_living", True):
        living = privacy.living_people(data, root, int(cfg["privacy"].get("living_years", 100)))
        data = privacy.redact(data, living)
    return data, living


def build(site_dir, out=None, base_url=None):
    site_dir = Path(site_dir).resolve()
    out = Path(out).resolve() if out else site_dir / "_site"
    cfg, raw = load_site(site_dir)
    if base_url is not None:   # e.g. the GitHub Pages address, known only when publishing
        cfg["base_url"] = base_url if not base_url or base_url.endswith("/") else base_url + "/"
    errors, warnings = validate(raw, site_dir, cfg)
    if errors:
        raise BuildError(m("family_tree.json has errors (see `gene validate`):\n  ", "в family_tree.json ошибки (подробно: `gene validate`):\n  ")
                         + "\n  ".join(errors[:30]))
    merged = {s["id"]: s["merged_into"] for s in raw["sources"] if s.get("merged_into") and not s.get("hidden")}
    data, living = public_data(cfg, raw)
    root = cfg["root_person"] or data["root_person_id"]
    cache = site_dir / ".cache"

    tmp = out.with_name(out.name + ".build")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    web = ENGINE / "web"
    for name in ("app.js", "app.css", "languages.js"):
        shutil.copy2(web / name, tmp / name)
    shutil.copytree(web / "vendor", tmp / "vendor")
    content = site_dir / "content"
    story = (content / "story.html").read_text(encoding="utf-8") if (content / "story.html").exists() else ""
    bios = (content / "bios.html").read_text(encoding="utf-8") if (content / "bios.html").exists() else ""
    news = (content / "news.html").read_text(encoding="utf-8") if (content / "news.html").exists() else ""
    help_page = ENGINE / "help.html"
    if story:
        story = tag_story_places(story, (cfg.get("story") or {}).get("places", []))
        (tmp / "story.html").write_text(story, encoding="utf-8")
    if bios:
        (tmp / "bios.html").write_text(bios, encoding="utf-8")
    for folder in ("img", "geo"):
        if (site_dir / folder).is_dir():
            shutil.copytree(site_dir / folder, tmp / folder)
    template = (web / "index.html").read_text(encoding="utf-8")
    (tmp / "index.html").write_text(fill_index(template, cfg, bool(story), bool(news), help_page.exists()), encoding="utf-8")

    # documents, previews, restored copies
    sources = [{k: v for k, v in s.items() if k not in ("email_subject", "email_date", "email_message_id")} for s in data["sources"]]
    (tmp / "sources" / "thumbs").mkdir(parents=True)
    used_names = set()
    for s in sources:
        for k in ("file", "back"):
            if s.get(k):
                dest = tmp / s[k]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(site_dir / s[k], dest)
        f = s.get("file", "")
        stem = Path(f).stem
        while stem in used_names:
            stem += "-" + s["id"]
        used_names.add(stem)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            thumb = make_thumb(site_dir / f, tmp / "sources" / "thumbs" / (stem + ".jpg"), 360, cache / "thumbs", quality=80)
            s["thumb"] = str(thumb.relative_to(tmp)).replace("\\", "/")
        elif f.lower().endswith(".pdf"):
            prev = pdf_preview(site_dir / f, int(s.get("preview_page") or 1), cache / "pdf-previews")
            if prev:
                thumb = make_thumb(prev, tmp / "sources" / "thumbs" / (stem + ".jpg"), 360, cache / "thumbs", transpose=False, quality=80)
                s["thumb"] = str(thumb.relative_to(tmp)).replace("\\", "/")
    for pl in data.get("places", []):
        for md in pl.get("media", []):
            if md.get("file") and not (tmp / md["file"]).exists():
                (tmp / md["file"]).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(site_dir / md["file"], tmp / md["file"])
    # files referenced from the story / bios / news pages
    for rel in set(re.findall(r'(?:src|href)="((?:sources|img)/[^"?#]+)"', story + bios + news)):
        src = site_dir / rel
        if not src.is_file():
            raise BuildError(m(f"content page refers to a missing file: {rel}", f"страница content/ ссылается на отсутствующий файл: {rel}"))
        if not (tmp / rel).exists():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tmp / rel)
    restored = []
    manifest = site_dir / "sources" / "restored" / "manifest.json"
    if manifest.exists():
        known = {s["id"] for s in sources}
        for r in json.loads(manifest.read_text(encoding="utf-8")):
            if r.get("skipped") or r.get("source_id") not in known:
                continue
            item = {k: r.get(k) for k in ("source_id", "method", "caveats", "date")}
            for v in ("bw", "color"):
                rel = r.get(v)
                if rel and (site_dir / rel).is_file():
                    (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(site_dir / rel, tmp / rel)
                    thumb = make_thumb(site_dir / rel, tmp / "sources" / "thumbs" / (Path(rel).stem + ".jpg"), 960,
                                       cache / "thumbs", quality=80, optimize=True, progressive=True)
                    item[v], item[v + "_thumb"] = rel, str(thumb.relative_to(tmp)).replace("\\", "/")
            if item.get("bw") or item.get("color"):
                restored.append(item)

    people = data["people"]
    site = config.public(cfg)
    if story:
        site["v_story"] = sha(story)
    if bios:
        site["v_bios"] = sha(bios)
    payload = {
        "site": site,
        "snapshot_date": __import__("datetime").date.today().isoformat(),
        "root_person_id": root,
        "start_focus": cfg["start_person"] or root,
        "merged_sources": merged,
        "counts": {"named_people": sum(1 for x in people if not x.get("placeholder")),
                   "possible_relatives": sum(1 for x in people if not x.get("placeholder") and x.get("research_status") == "unlinked_candidate"),
                   "unnamed_placeholders": sum(1 for x in people if x.get("placeholder") and not x.get("group")),
                   "families": len(data["families"])},
        "people": people,
        "families": data["families"],
        "sources": sources,
        "corrections": data.get("corrections", []),
        "leads": data.get("research_leads", []),
        "branches": cfg["branches"],
        "places": data.get("places", []),
        "place_groups": data.get("place_groups", []),
        "place_routes": data.get("place_routes", []),
        "questions": [q for q in cfg["questions"] if q.get("person") not in living],
        "unmatched_profiles": data.get("unmatched_profiles"),
        "research_log": data.get("research_log", []),
        "surnames": data.get("surnames", {}),
        "restored": restored,
        "bios": re.findall(r'<article class="bio" id="bio-(I\d+)"', bios),
    }
    (tmp / "data.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (tmp / "family_tree.ged").write_text(ged_export.build(data, cfg["title"]), encoding="utf-8")

    pages = discovery.Pages(tmp, data, cfg, living, bool(story), bool(news))
    pages.build(story, news, help_page.read_text(encoding="utf-8") if help_page.exists() else "")
    indexed = pages.finish()

    versions = {"i18n": sha("".join(sorted(p.read_text(encoding="utf-8") for p in (ENGINE / "i18n").glob("*.json"))))}
    report = localize.build_locales(tmp, cfg, site_dir, versions)

    # cache-busting versions for the shared scripts and styles
    for page in [tmp / "index.html"] + [tmp / lang / "index.html" for lang in cfg["languages"][1:]]:
        text = page.read_text(encoding="utf-8")
        for name in ("app.js", "app.css"):
            v = sha((tmp / name).read_bytes())
            text = re.sub(r'((?:src|href)="(?:\.\./)?' + re.escape(name) + r')"', r'\1?v=' + v + '"', text)
        page.write_text(text, encoding="utf-8")

    old = out.with_name(out.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if out.exists():
        out.rename(old)
    tmp.rename(out)
    if old.exists():
        shutil.rmtree(old)
    return {"out": out, "people": len(people), "living": len(living), "families": len(data["families"]),
            "sources": len(sources), "indexed": indexed, "warnings": warnings, "missing_translations": report}
