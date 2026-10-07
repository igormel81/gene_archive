"""Language editions of the built site.

The first language in site.json is published at the site root, the others in /<lang>/.
Two kinds of text are translated:

* the interface — the engine's dictionaries gene_archive/engine/i18n/<lang>.json
  ({"Russian source text": "translation"}); app.js looks strings up at run time through
  i18n/<lang>.js, HTML pages are translated here;
* your content (notes, titles, story pages) — optional dictionaries in the site folder,
  translations/<lang>.json in the same format. Missing content translations fall back to
  the original text unless site.json sets "strict_translations": true.

Only strings in Cyrillic are looked up: the interface source is Russian, and content in other
languages simply passes through. No translation service is contacted.
"""
import hashlib
import html
import json
import posixpath
import re
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from .config import UI_LANGUAGES

ENGINE_I18N = Path(__file__).resolve().parent / "engine" / "i18n"
CYR = re.compile("[А-Яа-яЁё]")
# fields of data.json that are identifiers, names or paths — never translated
KEEP = {"id", "person_id", "given_names", "surname", "display_name", "aliases", "sex", "kind", "status",
        "research_status", "relation_kind", "match", "slug", "group", "groups", "from_place", "to_place",
        "place_slugs", "place_event_kind", "url", "file", "thumb", "back", "bw", "color", "bw_thumb",
        "color_thumb", "source_ids", "identity_source_ids", "color", "base_url", "credit_url", "gedcom_id",
        "living", "placeholder", "source_id", "lat", "lon", "sort_year", "partners", "children",
        "adopted_children", "probable_children", "people", "sources", "focus", "person", "quick_focus_person",
        "surname_variants", "branch_tags", "v_story", "v_bios", "comments", "bios", "merged_sources",
        "root_person_id", "start_focus", "snapshot_date"}
PATH_KEYS = {"file", "thumb", "back", "bw", "color", "bw_thumb", "color_thumb"}
SOFT = {"corrections", "research_log"}   # journals: without a translation they stay in the original
# files and folders shared by all languages (everything else exists per language)
SHARED = ("app.js", "app.css", "languages.js", "vendor/", "sources/", "img/", "geo/", "i18n/",
          "family_tree.ged", "api/", "robots.txt", "sitemap.xml", "favicon")
FRAGMENTS = ("story.html", "bios.html")   # loaded by app.js, no header of their own


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def load_catalog(lang, site_dir=None):
    """Interface dictionary + the site's content dictionary for `lang`, keyed by digest."""
    catalog = {}
    path = ENGINE_I18N / f"{lang}.json"
    if path.exists():
        catalog.update({digest(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()})
    if site_dir:
        own = Path(site_dir) / "translations" / f"{lang}.json"
        if own.exists():
            catalog.update({digest(k.strip()): v for k, v in json.loads(own.read_text(encoding="utf-8")).items()})
    return catalog


class Missing(ValueError):
    pass


class Translator:
    def __init__(self, names, catalog=None, strict=False):
        self.names = set(names)
        self.catalog = catalog          # None = collect mode (gene translations missing)
        self.strict = strict
        self.strings = set()
        self.missing = set()

    def soft(self, text):
        try:
            return self(text, strict=False)
        except Missing:
            return text

    def paragraph(self, key):
        return None if self.catalog is None else self.catalog.get(digest(key))

    def __call__(self, text, strict=None):
        core = text.strip()
        if not CYR.search(core) or core in self.names:
            return text
        self.strings.add(core)
        if self.catalog is None:
            return text
        key = digest(core)
        if key not in self.catalog:
            self.missing.add(core)
            if self.strict if strict is None else strict:
                raise Missing("Missing translation: " + core[:100])
            return text
        translated = self.catalog[key]
        tags = r"</?[A-Za-z][^>]*>"
        if re.findall(tags, core) != re.findall(tags, translated):
            raise ValueError("Translation changed HTML markup: " + core[:100])
        return text[:len(text) - len(text.lstrip())] + translated + text[len(text.rstrip()):]


def shared(rel):
    return rel.startswith(SHARED) or rel.endswith((".css", ".ged"))


def make_url_mapper(lang_prefix, page, base_url):
    """URL rewriting for a page copied from the root edition into /<lang>/.

    Relative links to shared files gain '../'; absolute links into the site (base_url…)
    point to the same page of this language."""
    page_dir = posixpath.dirname(page)

    def url(u):
        if not u or u.startswith(("#", "data:", "mailto:", "tel:", "javascript:", "//")):
            return u
        if base_url and u.startswith(base_url):
            rel = u[len(base_url):]
            return u if not lang_prefix or shared(rel) else base_url + lang_prefix + rel
        if re.match(r"[a-z]+:", u):
            return u
        if not lang_prefix:
            return u
        path, _, rest = u.partition("#")
        path, q, query = path.partition("?")
        target = posixpath.normpath(posixpath.join(page_dir, path)) if path else page
        if target.startswith(".."):
            return u
        if path and shared(target):
            path = "../" + path
        return path + (q + query if q else "") + ("#" + rest if rest else "") if (path or rest or q) else u
    return url


BLOCKS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "dt", "dd", "td", "th", "summary",
          "blockquote", "label", "legend", "caption"}
INLINE = {"a", "b", "strong", "i", "em", "span", "small", "kbd", "u", "br", "sup", "sub", "code", "abbr",
          "time", "mark", "s", "q", "cite"}
TOKEN = re.compile(r"<(/?)(\d+)(/?)>")
TEXT_ATTRS = {"title", "alt", "placeholder", "aria-label"}
VOID = ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr")


class Page(HTMLParser):
    """Translates an HTML page. A block (paragraph, list item, caption…) with inline links and emphasis is
    translated whole: tags become markers <1>…</1>, <2/> and the key is the whole paragraph. Without a
    whole-paragraph translation the block is translated piece by piece between tags."""

    def __init__(self, tr, lang, url):
        super().__init__(convert_charrefs=True)
        self.tr, self.lang, self.url = tr, lang, url
        self.out, self.stack = [], []
        self.script_kind = None
        self.cap = None

    def _flush(self):
        cap, self.cap = self.cap, None
        if not cap:
            return
        events = cap[1]
        key, tags, n, open_ids = [], [], 0, []
        for ev in events:
            if ev[0] == "data":
                key.append(ev[1].replace("<", "&lt;"))
            elif ev[0] == "start":
                n += 1; tags.append(ev); open_ids.append((ev[1], n)); key.append(f"<{n}>")
            elif ev[0] == "startend":
                n += 1; tags.append(ev); key.append(f"<{n}/>")
            elif ev[0] == "end":
                for j in range(len(open_ids) - 1, -1, -1):
                    if open_ids[j][0] == ev[1]:
                        key.append(f"</{open_ids[j][1]}>"); open_ids.pop(j); break
        text = "".join(key)
        core = text.strip()
        whole = bool(tags) and bool(CYR.search(core)) and not open_ids
        if whole:
            translated = self.tr.paragraph(core)
            if translated is not None and self._replay(text, core, translated, tags):
                return
        for ev in events:
            getattr(self, "_ev_" + ev[0])(*ev[1:])

    def _replay(self, text, core, translated, tags):
        if sorted(TOKEN.findall(core)) != sorted(TOKEN.findall(translated)):
            raise ValueError("Translation changed paragraph markup: " + core[:100])
        self.out.append(html.escape(text[:len(text) - len(text.lstrip())], quote=False))
        pos = 0
        for mm in TOKEN.finditer(translated):
            self.out.append(html.escape(html.unescape(translated[pos:mm.start()]), quote=False))
            ev = tags[int(mm.group(2)) - 1]
            if mm.group(1):
                self.out.append("</" + ev[1] + ">")
            else:
                self._emit_start(ev[1], ev[2])
            pos = mm.end()
        self.out.append(html.escape(html.unescape(translated[pos:]), quote=False))
        self.out.append(html.escape(text[len(text.rstrip()):], quote=False))
        return True

    def title(self, s):
        """«Имя (1890–1950), Место — Семейный архив»: names stay, every other part is translated by itself."""
        parts = re.split(r"( — |, | \(|\))", s)
        return "".join(p if i % 2 else self.tr.soft(p) for i, p in enumerate(parts))

    def _ev_start(self, tag, attrs): self._start(tag, attrs)
    def _ev_startend(self, tag, attrs): self._start(tag, attrs)
    def _ev_end(self, tag): self._end(tag)
    def _ev_data(self, s): self._data(s)

    def handle_starttag(self, tag, attrs):
        if self.cap is not None:
            if tag in INLINE:
                self.cap[1].append(("start" if tag != "br" else "startend", tag, attrs)); return
            self._flush()
        self._start(tag, attrs)
        if tag in BLOCKS and self.script_kind is None:
            self.cap = [tag, []]

    def handle_startendtag(self, tag, attrs):
        if self.cap is not None:
            if tag in INLINE:
                self.cap[1].append(("startend", tag, attrs)); return
            self._flush()
        self._start(tag, attrs)

    def handle_endtag(self, tag):
        if self.cap is not None:
            if tag in INLINE:
                self.cap[1].append(("end", tag)); return
            self._flush()
        self._end(tag)

    def handle_data(self, s):
        if self.cap is not None:
            self.cap[1].append(("data", s)); return
        self._data(s)

    def handle_decl(self, s): self.out.append("<!" + s + ">")

    def handle_comment(self, s):
        if self.cap is not None:
            self._flush()
        self.out.append("<!--" + s + "-->")

    def _start(self, tag, attrs):
        self._emit_start(tag, attrs)
        if tag not in VOID:
            self.stack.append(tag)

    def _emit_start(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            attrs["lang"] = self.lang
        if tag == "script":
            self.script_kind = attrs.get("type", "")
        for k, v in list(attrs.items()):
            if v is None:
                continue
            if tag == "meta" and k == "content" and attrs.get("property") == "og:title":
                attrs[k] = self.title(v)
            elif k in TEXT_ATTRS or (tag == "meta" and k == "content" and (
                    attrs.get("name") == "description" or attrs.get("property") in ("og:description", "og:site_name"))):
                attrs[k] = self.tr(v)
            if k in ("href", "src") or (tag == "meta" and attrs.get("property") == "og:url" and k == "content"):
                attrs[k] = self.url(v)
        self.out.append("<" + tag + "".join(" " + k + ("" if v is None else '="' + html.escape(v, quote=True) + '"')
                                            for k, v in attrs.items()) + ">")

    def _end(self, tag):
        self.out.append("</" + tag + ">")
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]
        if tag == "script":
            self.script_kind = None

    def _data(self, s):
        if self.stack and self.stack[-1] == "script":
            if self.script_kind == "application/ld+json":
                def schema(v, key=""):
                    if isinstance(v, dict): return {k: schema(x, k) for k, x in v.items()}
                    if isinstance(v, list): return [schema(x, key) for x in v]
                    if not isinstance(v, str): return v
                    if key == "inLanguage": return self.lang
                    if key in ("url", "@id") or v.startswith(("http://", "https://")): return self.url(v)
                    if key == "name": return self.title(v)
                    if key == "description": return self.tr(v)
                    return v
                s = json.dumps(schema(json.loads(s)), ensure_ascii=False).replace("<", "\\u003c")
            self.out.append(s)
        elif self.stack and self.stack[-1] == "style":
            self.out.append(s)
        elif self.stack and self.stack[-1] == "title":
            self.out.append(html.escape(self.title(s), quote=False))
        else:
            self.out.append(html.escape(self.tr(s), quote=False))

    def render(self, source):
        self.feed(source)
        self.close()
        if self.cap is not None:
            self._flush()
        return "".join(self.out)


def data_translate(value, tr, key="", soft=False, prefix=""):
    if key in SOFT:
        soft = True
    if key in KEEP and not isinstance(value, dict) and not (isinstance(value, list) and any(isinstance(x, dict) for x in value)):
        # identifiers, names, paths and lists of ids; lists of records (people, sources…) are walked below
        if prefix and key in PATH_KEYS and isinstance(value, str) and not re.match(r"[a-z]+:", value):
            return prefix + value
        return value
    if isinstance(value, dict):
        return {k: data_translate(v, tr, k, soft, prefix) for k, v in value.items()}
    if isinstance(value, list):
        return [data_translate(v, tr, key, soft, prefix) for v in value]
    if not isinstance(value, str):
        return value
    return tr.soft(value) if soft else tr(value)


def names_in(data):
    names = set()
    for p in data["people"]:
        names.update(p.get(k, "") for k in ("given_names", "surname", "display_name"))
        names.update(p.get("aliases", []))
    return names


def html_pages(out):
    """Root-edition HTML pages (not inside other language folders or shared folders)."""
    return sorted(p for p in out.rglob("*.html")
                  if p.relative_to(out).parts[0] not in tuple(UI_LANGUAGES) + ("sources", "vendor", "img", "i18n"))


def language_nav(cfg, lang, page):
    langs = cfg["languages"]
    if len(langs) < 2:
        return ""
    depth = page.count("/")
    up = "../" * (depth + (0 if lang == langs[0] else 1))   # path from this page to the site root
    rel = "" if page == "index.html" else page.replace("/index.html", "/")
    label = {"ru": "Язык сайта", "en": "Site language", "ro": "Limba site-ului"}.get(lang, "Language")
    links = "".join(
        f'<a data-site-lang="{x}" lang="{x}" hreflang="{x}"' + (' class="on" aria-current="true"' if x == lang else "")
        + f' href="{up}{"" if x == langs[0] else x + "/"}{rel}">{UI_LANGUAGES[x]["name"]}</a>' for x in langs)
    return (f'<div class="language-tools"><details class="more-menu language-nav"><summary aria-label="{label}">'
            f'{UI_LANGUAGES[lang]["name"]} <span aria-hidden="true">▾</span></summary>'
            f'<nav class="more-list" aria-label="{label}">{links}</nav></details></div>')


def locale_js(lang):
    info = UI_LANGUAGES[lang]
    strings = {}
    path = ENGINE_I18N / f"{lang}.json"
    if path.exists():
        strings = json.loads(path.read_text(encoding="utf-8"))
    payload = {"lang": lang, "locale": info["locale"], "plural": info["plural"], "strings": strings}
    return "window.GENE_LOCALE = " + json.dumps(payload, ensure_ascii=False, sort_keys=True) + ";\n"


def build_locales(out, cfg, site_dir, data_versions):
    """Turns the Russian-interface build in `out` into the configured language editions."""
    out = Path(out)
    langs = cfg["languages"]
    base = cfg["base_url"]
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    pages = [(str(p.relative_to(out)).replace("\\", "/"), p.read_text(encoding="utf-8")) for p in html_pages(out)]
    (out / "i18n").mkdir(exist_ok=True)
    report = {}
    for n, lang in enumerate(langs):
        prefix = "" if n == 0 else lang + "/"
        catalog = load_catalog(lang, site_dir) if lang != "ru" else None   # Russian is the interface source
        tr = Translator(names_in(data), catalog, strict=cfg["strict_translations"])
        target = out / prefix if prefix else out
        target.mkdir(exist_ok=True)
        (out / "i18n" / f"{lang}.js").write_text(locale_js(lang), encoding="utf-8")
        localized = data_translate(data, tr, prefix="../" if prefix else "")
        (target / "data.json").write_text(json.dumps(localized, ensure_ascii=False), encoding="utf-8")
        for page, text in pages:
            depth = page.count("/")
            root = "../" * (depth + (1 if prefix else 0))
            text = text.replace("<!--gene:scripts-->",
                                f'<script src="{"../" * depth}i18n/{lang}.js?v={data_versions.get("i18n", "")}"></script>')
            text = text.replace("<!--gene:root-->", f"window.GENE_ROOT = {json.dumps(root)};")
            text = Page(tr, lang, make_url_mapper(prefix, page, base)).render(text)
            if page not in FRAGMENTS:
                text = decorate(text, cfg, lang, page)
            dest = target / page
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
        report[lang] = sorted(tr.missing)
    # sitemap: every language edition of every listed page
    sm = out / "sitemap.xml"
    if base and sm.exists() and len(langs) > 1:
        ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
        ET.register_namespace("", ns)
        tree = ET.parse(sm)
        urls = [e.text for e in tree.findall(".//{" + ns + "}loc")]
        for lang in langs[1:]:
            for u in urls:
                item = ET.SubElement(tree.getroot(), "{" + ns + "}url")
                ET.SubElement(item, "{" + ns + "}loc").text = base + lang + "/" + u[len(base):]
        tree.write(sm, encoding="utf-8", xml_declaration=True)
    return report


def decorate(text, cfg, lang, page):
    langs, base = cfg["languages"], cfg["base_url"]
    rel = "" if page == "index.html" else page.replace("/index.html", "/")
    head = ""
    if base and len(langs) > 1:
        head = "".join(f'<link rel="alternate" hreflang="{x}" href="{base}{"" if x == langs[0] else x + "/"}{rel}">' for x in langs)
        head += f'<link rel="alternate" hreflang="x-default" href="{base}{rel}">'
    depth = page.count("/") + (0 if lang == langs[0] else 1)
    if len(langs) > 1:
        head += f'<script src="{"../" * depth}languages.js" defer></script>'
    text = text.replace("</head>", head + "</head>", 1)
    nav = language_nav(cfg, lang, page)
    if nav:
        if 'class="bar bar-static"' in text:
            text = text.replace("</nav></header>", "</nav>" + nav + "</header>", 1)
        elif 'id="search-toggle"' in text:
            text = re.sub(r'(<button\b[^>]*id="search-toggle"[^>]*>.*?</button>)', lambda mm: mm[1] + nav, text, count=1, flags=re.S)
        else:
            text = re.sub(r"(<body\b[^>]*>)", lambda mm: mm[1] + nav, text, count=1)
    return text
