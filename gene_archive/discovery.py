"""Static pages for search engines, sharing and readers without JavaScript.

people/<id>.html, people/index.html, surnames/<slug>.html, history.html, news.html,
sitemap.xml and robots.txt (the last two only when site.json has base_url).
Texts here are written in the interface source language (Russian) and translated
by localize.py like every other page.
"""
import html
import json
import re
import unicodedata
from xml.etree import ElementTree as ET

STYLE = """body{display:block}main.archive-page{max-width:820px;margin:auto;padding:28px 20px 64px}
.archive-page p,.archive-page li{line-height:1.65}.archive-page h1{font-size:clamp(27px,5vw,40px)}
.archive-page li{margin-bottom:8px}.archive-page .notice{border-left:3px solid var(--accent);padding:12px 16px;background:var(--paper)}
.bar-static{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px}.bar-static .tabs a{padding:8px 10px}
.bar-static .language-tools{margin-left:auto}.archive-page p{margin:0 0 14px}"""
TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяіїєґ",
              ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u",
               "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya", "i", "yi", "ye", "g"]))
YEAR = re.compile(r"(ABT |AFT |BEF |EST |CAL )?(\d{4})")


def esc(value):
    return html.escape(str(value), quote=True)


def plural(n, one, few, many):
    n = abs(n) % 100
    return many if 10 < n < 20 else one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


def slugify(s):
    s = "".join(TR.get(c, c) for c in s.lower())
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"


def ld(value):
    return '<script type="application/ld+json">' + json.dumps(value, ensure_ascii=False).replace("<", "\\u003c") + "</script>"


def surname_key(s, variants):
    """As surnameKey in app.js: feminine form → masculine, site-specific spellings merged."""
    s = (s or "").strip()
    if not s:
        return ""
    if s.endswith("ská"): s = s[:-3] + "ský"
    elif s.endswith("ová"): s = s[:-3]
    elif s.endswith("ская"): s = s[:-4] + "ский"
    elif s.endswith("цкая"): s = s[:-4] + "цкий"
    elif re.search(r"(ова|ева|ёва|ина|ына)$", s): s = s[:-1]
    return variants.get(s, s)


class Pages:
    def __init__(self, out, data, cfg, living, has_story, has_news):
        self.out, self.data, self.cfg, self.living = out, data, cfg, living
        self.has_story, self.has_news = has_story, has_news
        self.sources = {s["id"]: s for s in data["sources"]}
        self.byid = {p["id"]: p for p in data["people"]}
        self.place_name = {pl["slug"]: re.split(r"[:(]", pl["name"])[0].strip() for pl in data.get("places", [])}
        self.meta = {}   # page → (schema type, entity, indexable)

    # --- page frame
    def header(self, up):
        tabs = [("tree", "Древо"), ("people", "Люди"), ("places", "Места"), ("sources", "Архив")]
        if self.has_story:
            tabs.append(("story", "История"))
        links = "".join(f'<a role="tab" class="tab" href="{up}#/{v}">{label}</a>' for v, label in tabs)
        if self.has_news:
            links = f'<a role="tab" class="tab tab-news" href="{up}news.html">Что нового</a>' + links
        return (f'<header class="bar bar-static"><div class="brand"><a class="eyebrow brand-home" href="{up}">'
                f'{esc(self.cfg["short_title"])}</a></div><nav class="tabs" role="tablist">{links}</nav></header>')

    def document(self, path, title, body, description, heading=True, kind="WebPage", entity=None, indexable=True):
        depth = path.count("/")
        up = "../" * depth
        page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — {esc(self.cfg["short_title"])}</title><meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{up}app.css"><style>{STYLE}</style></head><body>{self.header(up)}<main class="archive-page">
{'<h1>' + esc(title) + '</h1>' if heading else ''}{body}</main></body></html>"""
        dest = self.out / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page, encoding="utf-8")
        self.meta[path] = (kind, entity, indexable)

    # --- helpers
    def years(self, p):
        def year(ev):
            mm = YEAR.match(str((p.get(ev) or {}).get("date", "")))
            return ("~" if mm and mm[1] else "") + mm[2] if mm else ""
        b, d = year("birth"), year("death")
        return f'{b or "?"}–{d}' if d else b

    def place_of(self, p):
        slugs = []
        for ev in ("birth", "death", "burial"):
            slugs += (p.get(ev) or {}).get("place_slugs", [])
        for r in p.get("residences") or []:
            slugs += r.get("place_slugs", [])
        return next((self.place_name[x] for x in slugs if x in self.place_name), "")

    def title_of(self, p):
        if p["id"] in self.living:
            return p["display_name"]
        y, pl = self.years(p), self.place_of(p)
        return p["display_name"] + (f" ({y})" if y else "") + (f", {pl}" if pl else "")

    def person_li(self, p, up):
        if p["id"] in self.living:
            return f'<li><span>{esc(p.get("relation") or "Ныне живущий родственник")}</span></li>'
        y, pl = self.years(p), self.place_of(p)
        return (f'<li><a href="{up}people/{p["id"]}.html"><b>{esc(p["display_name"])}</b></a>'
                + (f' <span class="yr">{esc(y)}</span>' if y else "") + (f' <span class="pl">{esc(pl)}</span>' if pl else "") + "</li>")

    # --- pages
    def person(self, p):
        pid, name = p["id"], p["display_name"]
        path = f"people/{pid}.html"
        body = f'<p>{esc(p.get("relation", ""))}</p>' if p.get("relation") else ""
        if pid in self.living:
            body += "<p class=\"notice\">Сведения о ныне живущих людях на сайте не публикуются.</p>"
            self.document(path, name, body, "Сведения о ныне живущих людях на сайте не публикуются.", indexable=False)
            return
        if p.get("research_status") == "unlinked_candidate":
            body += '<p class="notice">Возможная родня: связь с нашей семьёй не установлена.</p>'
        for key, label in (("birth", "Рождение"), ("death", "Смерть"), ("burial", "Погребение")):
            ev = p.get(key) or {}
            values = [ev.get("date"), ev.get("place_as_recorded")]
            if any(values):
                body += f"<p><b>{label}:</b> " + esc(" · ".join(str(v) for v in values if v)) + "</p>"
        if p.get("aliases"):
            body += "<p><b>Варианты имени:</b> " + esc("; ".join(p["aliases"])) + "</p>"
        notes = p.get("notes", [])
        body += "".join("<p>" + esc(n) + "</p>" for n in notes)
        ids = set(p.get("identity_source_ids", []))
        for key in ("birth", "death", "burial"):
            ids.update((p.get(key) or {}).get("source_ids", []))
        for n in notes:
            ids.update(re.findall(r"\bS\d+\b", n))
        cited = [self.sources[i] for i in sorted(ids, key=lambda v: int(v[1:])) if i in self.sources]
        if cited:
            body += "<h2>Источники</h2><ul>"
            for s in cited:
                body += f'<li><a href="../#/sources?doc={s["id"]}">{esc(s["id"])}. {esc(s["title"])}</a>'
                if str(s.get("url", "")).startswith(("http://", "https://")):
                    body += f' — <a href="{esc(s["url"])}" rel="noopener">Оригинал</a>'
                if s.get("file"):
                    body += f' — <a href="../{esc(s["file"])}">Копия в архиве</a>'
                body += "</li>"
            body += "</ul>"
        body += f'<p><a href="../#/tree/{pid}?person={pid}">Открыть карточку в древе и семейные связи</a></p>'
        entity = {"@type": "Person", "name": name}
        if p.get("aliases"):
            entity["alternateName"] = p["aliases"]
        desc = "Сведения семейного архива, биографические заметки и источники."
        self.document(path, self.title_of(p), body, desc, kind="ProfilePage", entity=entity,
                      indexable=not p.get("placeholder"))

    def surname_groups(self):
        variants = self.cfg.get("surname_variants") or {}
        groups = {}
        for p in self.data["people"]:
            if p.get("placeholder"):
                continue
            keys = [surname_key(re.sub(r"\s*\(.*?\)", "", p.get("surname") or ""), variants)]
            for mm in re.findall(r"\(([^)]*)\)", p["display_name"]):
                keys += [surname_key(x.strip(), variants) for x in mm.split(",") if re.match(r"[A-ZА-ЯЁ]", x.strip())]
            for k in dict.fromkeys(x for x in keys if x):
                groups.setdefault(k, []).append(p["id"])
        return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    def surname(self, key, ids):
        people = [self.byid[i] for i in ids]
        dead = [q for q in people if q["id"] not in self.living]
        alive = len(people) - len(dead)
        years = [int(mm[2]) for q in dead for ev in ("birth", "death")
                 for mm in [YEAR.match(str((q.get(ev) or {}).get("date", "")))] if mm]
        counts = {}
        for q in dead:
            for ev in [q.get(e) or {} for e in ("birth", "death", "burial")] + list(q.get("residences") or []):
                for x in ev.get("place_slugs", []):
                    counts[x] = counts.get(x, 0) + 1
        places = [x for x, _ in sorted(counts.items(), key=lambda kv: -kv[1]) if x in self.place_name][:6]
        slug = slugify(key)
        path = f"surnames/{slug}.html"
        body = f'<header class="fam-hero"><p class="eyebrow">Фамилия в семейном архиве</p><h1>{esc(key)}</h1>'
        if places:
            body += '<p class="fam-route">' + " · ".join(
                f'<a href="../#/places?place={x}">{esc(self.place_name[x])}</a>' for x in places) + "</p>"
        body += '<div class="fam-stats">'
        body += f'<div><b>{len(people)}</b><span>{plural(len(people), "человек", "человека", "человек")}</span></div>'
        if years:
            body += f"<div><b>{min(years)}–{max(years)}</b><span>годы</span></div>"
        body += "</div></header>"
        story = (self.data.get("surnames") or {}).get(key, {})
        if story.get("history"):
            body += '<section class="fam-story"><h2>История рода</h2>' + "".join(f"<p>{esc(x)}</p>" for x in story["history"]) + "</section>"
        body += '<section class="fam-all"><h2>Люди</h2><ul class="fam-people">'
        body += "".join(self.person_li(q, "../") for q in sorted(dead, key=lambda q: (self.years(q) or "9999", q["display_name"])))
        body += "</ul>"
        if alive:
            body += f'<p class="fam-alive"><span>Ныне живущих:</span> <b>{alive}</b>. <span>Сведения о них не публикуются.</span></p>'
        body += "</section>"
        self.document(path, key, '<div class="fam-page">' + body + "</div>",
                      "Родословная, документы, места и годы жизни.", heading=False, kind="CollectionPage")
        return slug, len(people)

    def build(self, story_html, news_html, help_html=""):
        names = sorted(self.data["people"], key=lambda p: p["display_name"])
        for p in names:
            if not p.get("placeholder"):
                self.person(p)
        fam_links = []
        for key, ids in self.surname_groups():
            if len(ids) >= self.cfg["min_surname_page"]:
                slug, n = self.surname(key, ids)
                fam_links.append(f'<li><a href="../surnames/{slug}.html">{esc(key)}</a> <span>{n}</span></li>')
        index = ""
        if fam_links:
            index += '<h2>Фамилии</h2><ul class="fam-list">' + "".join(fam_links) + "</ul>"
        index += "<h2>Все люди</h2><ul>" + "".join(self.person_li(p, "../") for p in names if not p.get("placeholder")) + "</ul>"
        self.document("people/index.html", "Люди семейного архива", index, "Алфавитный указатель людей семейного архива.",
                      kind="CollectionPage")
        if story_html:
            history = re.sub(r'<a([^>]*?)data-p="(I\d+)"([^>]*)>', lambda mm: f'<a{mm[1]}href="people/{mm[2]}.html"{mm[3]}>', story_html)
            self.document("history.html", "История семьи", history, "История семьи по документам и воспоминаниям.", heading=False)
        if news_html:
            self.document("news.html", "Что нового", news_html, "Новые находки семейного архива.", heading=False)
        if help_html:
            self.document("help.html", "Как пользоваться сайтом", help_html, "Как устроен семейный архив и как дописать в него то, что вы знаете.")
        self.meta["index.html"] = ("WebSite", None, True)

    def finish(self):
        """Robots meta, canonical links, Open Graph, JSON-LD and the sitemap for every page."""
        base = self.cfg["base_url"]
        head_html = self.cfg.get("head_html") or ""
        urls = []
        for name, (kind, entity, indexable) in self.meta.items():
            path = self.out / name
            text = path.read_text(encoding="utf-8")
            title = html.unescape(re.search(r"<title>(.*?)</title>", text, re.S)[1])
            d = re.search(r'<meta name="description" content="([^"]*)"', text)
            description = html.unescape(d[1]) if d else title
            text = re.sub(r'<meta name="robots"[^>]*>\s*', "", text)
            head = f'<meta name="robots" content="{"index, follow" if indexable else "noindex, follow"}">\n'
            head += f'<meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}">'
            head += f'<meta property="og:description" content="{esc(description)}"><meta property="og:site_name" content="{esc(self.cfg["title"])}">\n'
            if base:
                url = base + ("" if name == "index.html" else name.replace("/index.html", "/"))
                head += f'<link rel="canonical" href="{esc(url)}"><meta property="og:url" content="{esc(url)}">\n'
                schema = {"@context": "https://schema.org", "@type": kind, "url": url, "name": title,
                          "description": description, "inLanguage": "ru"}
                if entity:
                    schema["mainEntity"] = entity
                head += ld(schema)
                if indexable:
                    urls.append(url)
            text = text.replace("</head>", head + head_html + "\n</head>", 1)
            path.write_text(text, encoding="utf-8")
        if base:
            ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
            ET.register_namespace("", ns)
            root = ET.Element("{" + ns + "}urlset")
            for u in urls:
                ET.SubElement(ET.SubElement(root, "{" + ns + "}url"), "{" + ns + "}loc").text = u
            ET.ElementTree(root).write(self.out / "sitemap.xml", encoding="utf-8", xml_declaration=True)
            path = __import__("urllib.parse").parse.urlsplit(base).path or "/"
            (self.out / "robots.txt").write_text(f"User-agent: *\nDisallow: {path}api/\nSitemap: {base}sitemap.xml\n", encoding="utf-8")
        return len(urls)
