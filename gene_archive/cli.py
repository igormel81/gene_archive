"""gene — command line of gene-archive.

  gene init <folder>               new site from a template (or --example for the demo family)
  gene import tree.ged <folder>    new site from a GEDCOM file (MyHeritage, Gramps, Ancestry, Geni…)
  gene validate <folder>           check family_tree.json and site.json
  gene build <folder> [-o out]     build the static site into <folder>/_site
  gene serve <folder>              build, then serve the site with comments on http://127.0.0.1:8111
  gene comments <folder> list|approve ID|hide ID|done ID "note"   moderate relatives' comments
  gene translations <folder> <lang>   list texts of your site without a translation into <lang>

Messages are in Russian when the system language is Russian (or GENE_LANG=ru).
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from . import __version__
from .messages import m

EXAMPLE = Path(__file__).resolve().parent.parent / "example"


def cmd_init(args):
    dest = Path(args.folder)
    if dest.exists() and any(dest.iterdir()):
        sys.exit(m(f"{dest} is not empty", f"папка {dest} не пустая"))
    if args.example:
        if not EXAMPLE.is_dir():
            sys.exit(m("the example is not installed with this copy (clone the repository)", "пример не установлен (склонируйте репозиторий)"))
        shutil.copytree(EXAMPLE, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("_site*", ".cache"))
        print(m(f"Demo site copied to {dest}. Next: gene serve {dest}", f"Пример скопирован в {dest}. Дальше: gene serve {dest}"))
        return
    lang = args.lang
    (dest / "sources").mkdir(parents=True, exist_ok=True)
    (dest / "content").mkdir(exist_ok=True)
    you = {"ru": ("Иван Петрович", "Иванов", "Иванов Иван Петрович"), "en": ("John", "Smith", "Smith John")}.get(lang, ("John", "Smith", "Smith John"))
    data = {
        "schema_version": "1.0", "root_person_id": "I1",
        "people": [{"id": "I1", "given_names": you[0], "surname": you[1], "display_name": you[2], "sex": "M",
                    "relation": m("compiler of the tree", "составитель древа"), "identity_source_ids": [], "aliases": [], "notes": []}],
        "families": [], "sources": [], "places": [], "place_groups": [], "place_routes": [],
        "research_leads": [], "corrections": [], "research_log": [], "surnames": {},
    }
    (dest / "family_tree.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    title = {"ru": "Семейный архив", "en": "Family archive"}.get(lang, "Family archive")
    site = {"title": title, "description": "", "languages": [lang] + [x for x in ("en", "ru") if x != lang][:1],
            "comments": False, "questions": [], "branches": []}
    (dest / "site.json").write_text(json.dumps(site, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (dest / ".gitignore").write_text("_site/\n_site.*/\n.cache/\n.gene-state/\n", encoding="utf-8")
    print(m(f"New site in {dest}. Edit family_tree.json and site.json, then: gene serve {dest}\n"
            "How to start the research: docs/research-guide.md",
            f"Новый сайт в {dest}. Заполните family_tree.json и site.json, затем: gene serve {dest}\n"
            "С чего начать поиск: docs/research-guide.ru.md"))


def cmd_import(args):
    from . import ged_import
    dest = Path(args.folder)
    tree = dest / "family_tree.json"
    if tree.exists() and not args.force:
        sys.exit(m(f"{tree} exists (use --force to overwrite)", f"{tree} уже есть (перезаписать: --force)"))
    data, warnings = ged_import.import_gedcom_with_warnings(args.gedcom, root=args.root)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "sources").mkdir(exist_ok=True)
    tree.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not (dest / "site.json").exists():
        title = m("Family archive", "Семейный архив")
        (dest / "site.json").write_text(json.dumps({"title": title, "languages": [args.lang] + [x for x in ("en", "ru") if x != args.lang][:1],
                                                    "comments": False}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for w in warnings:
        print(m("warning: ", "предупреждение: ") + w)
    print(m(f"{len(data['people'])} people, {len(data['families'])} families, {len(data['sources'])} sources → {tree}",
            f"{len(data['people'])} человек, {len(data['families'])} семей, {len(data['sources'])} источников → {tree}"))


def cmd_validate(args):
    from .build import load_site
    from .validate import validate
    cfg, data = load_site(args.folder)
    errors, warnings = validate(data, Path(args.folder), cfg)
    for w in warnings:
        print(m("warning: ", "предупреждение: ") + w)
    for e in errors:
        print(m("ERROR: ", "ОШИБКА: ") + e)
    print(m(f"{len(errors)} errors, {len(warnings)} warnings", f"ошибок: {len(errors)}, предупреждений: {len(warnings)}"))
    return 1 if errors else 0


def run_build(folder, out=None, base_url=None):
    from .build import BuildError, build
    started = time.time()
    try:
        r = build(folder, out, base_url)
    except BuildError as e:
        sys.exit(str(e))
    missing = {k: v for k, v in r["missing_translations"].items() if v}
    print(m(f"{r['out']}: {r['people']} people ({r['living']} living, details hidden), {r['families']} families, "
            f"{r['sources']} documents; {time.time() - started:.1f} s",
            f"{r['out']}: {r['people']} человек (живых — {r['living']}, сведения скрыты), семей — {r['families']}, "
            f"документов — {r['sources']}; {time.time() - started:.1f} с"))
    for lang, items in missing.items():
        print(m(f"{lang}: {len(items)} texts without a translation (they stay in the original; list: gene translations {folder} {lang})",
                f"{lang}: {len(items)} текстов без перевода (остаются в оригинале; список: gene translations {folder} {lang})"))
    return r


def cmd_build(args):
    run_build(args.folder, args.out, args.base_url)


def cmd_serve(args):
    from .server import Settings, serve
    r = run_build(args.folder, args.out) if not args.no_build else None
    site = Path(args.out) if args.out else (r["out"] if r else Path(args.folder) / "_site")
    pin = args.pin
    cfg = Settings.from_env(site=site, state_dir=args.state or str(Path(args.folder) / ".gene-state"),
                            host=args.host, port=args.port, prefix=args.prefix)
    if pin:
        import hashlib
        cfg.pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    # plain http on this computer: browsers would drop a Secure cookie; behind an HTTPS proxy keep it Secure
    if args.insecure_cookie or (cfg.host in ("127.0.0.1", "localhost") and not cfg.trust_proxy):
        cfg.secure_cookie = False
    if args.moderate:
        cfg.moderate = True
    serve(cfg)


def cmd_comments(args):
    from .server import comments_db
    state = Path(args.state or Path(args.folder) / ".gene-state")
    if not (state / "comments.db").exists():
        sys.exit(m(f"no comments database in {state}", f"нет базы комментариев в {state}"))
    with comments_db(state) as conn:
        if args.action == "list":
            for r in conn.execute("SELECT * FROM comments ORDER BY id"):
                flag = m("hidden", "скрыт") if r["hidden"] else ("✓" if r["processed_at"] else "")
                print(f"#{r['id']} {r['created_at'][:16]} {r['person_id']} {r['author']}: {r['text'][:200]} {flag}")
            return
        if args.id is None:
            sys.exit(m("comment id is required", "нужен номер комментария"))
        if args.action == "approve":
            conn.execute("UPDATE comments SET hidden = 0 WHERE id = ?", (args.id,))
        elif args.action == "hide":
            conn.execute("UPDATE comments SET hidden = 1 WHERE id = ?", (args.id,))
        elif args.action == "done":
            conn.execute("UPDATE comments SET processed_at = ?, processed_note = ? WHERE id = ?",
                         (time.strftime("%Y-%m-%d"), args.note or "", args.id))
        print("ok")


def cmd_translations(args):
    from . import localize
    from .build import BuildError, build
    try:
        r = build(args.folder, args.out)
    except BuildError as e:
        sys.exit(str(e))
    items = r["missing_translations"].get(args.lang)
    if items is None:
        sys.exit(m(f"{args.lang} is not in site.json languages", f"языка {args.lang} нет в languages в site.json"))
    template = {s: "" for s in items}
    print(json.dumps(template, ensure_ascii=False, indent=2))
    sys.stderr.write(m(f"{len(items)} texts. Put translations into translations/{args.lang}.json in the site folder.\n",
                       f"Текстов: {len(items)}. Переводы — в translations/{args.lang}.json в папке сайта.\n"))
    _ = localize


def main(argv=None):
    p = argparse.ArgumentParser(prog="gene", description=m("Family archive site generator", "Генератор сайта семейного архива"))
    p.add_argument("--version", action="version", version=f"gene-archive {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help=m("create a new site", "создать новый сайт"))
    s.add_argument("folder")
    s.add_argument("--lang", default="ru" if m("en", "ru") == "ru" else "en", choices=["ru", "en", "ro"])
    s.add_argument("--example", action="store_true", help=m("copy the demo family", "скопировать демонстрационную семью"))
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("import", help=m("new site from a GEDCOM file", "новый сайт из файла GEDCOM"))
    s.add_argument("gedcom")
    s.add_argument("folder")
    s.add_argument("--root", help=m("root person (GEDCOM id like @I12@)", "главный человек (номер в GEDCOM, например @I12@)"))
    s.add_argument("--lang", default="ru" if m("en", "ru") == "ru" else "en", choices=["ru", "en", "ro"])
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_import)
    s = sub.add_parser("validate", help=m("check the data", "проверить данные"))
    s.add_argument("folder", nargs="?", default=".")
    s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("build", help=m("build the site", "собрать сайт"))
    s.add_argument("folder", nargs="?", default=".")
    s.add_argument("-o", "--out")
    s.add_argument("--base-url", help=m("public address of the site, overrides site.json", "адрес сайта, вместо base_url из site.json"))
    s.set_defaults(fn=cmd_build)
    s = sub.add_parser("serve", help=m("build and serve with comments", "собрать и запустить с комментариями"))
    s.add_argument("folder", nargs="?", default=".")
    s.add_argument("-o", "--out")
    s.add_argument("--host", default=None)
    s.add_argument("--port", type=int, default=None)
    s.add_argument("--prefix", default=None)
    s.add_argument("--pin", help=m("require this PIN to open the site", "открывать сайт только по этому PIN"))
    s.add_argument("--state", help=m("folder for comments.db", "папка для comments.db"))
    s.add_argument("--moderate", action="store_true", help=m("new comments wait for approval", "новые комментарии ждут одобрения"))
    s.add_argument("--insecure-cookie", action="store_true")
    s.add_argument("--no-build", action="store_true")
    s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("comments", help=m("moderate comments", "модерация комментариев"))
    s.add_argument("folder")
    s.add_argument("action", choices=["list", "approve", "hide", "done"])
    s.add_argument("id", nargs="?", type=int)
    s.add_argument("note", nargs="?")
    s.add_argument("--state")
    s.set_defaults(fn=cmd_comments)
    s = sub.add_parser("translations", help=m("texts without a translation", "тексты без перевода"))
    s.add_argument("folder")
    s.add_argument("lang")
    s.add_argument("-o", "--out")
    s.set_defaults(fn=cmd_translations)
    args = p.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
