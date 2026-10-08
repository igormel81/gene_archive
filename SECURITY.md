# Security / Безопасность

Family archives hold private data, so security reports matter.

Please report vulnerabilities **privately**: Security → *Report a vulnerability* on
https://github.com/igormel81/gene_archive (GitHub private advisories). Do not open a public issue.
Especially interesting: leaks of living people's details or hidden documents into the built site,
data.json or GEDCOM; the comments server (`gene_archive/server.py`); the online editor (`gene_archive/editor.py`: sign-in, sessions, CSRF, uploads, roles); path traversal; PIN bypass.

---

Семейные архивы хранят личные данные, поэтому сообщения об уязвимостях важны.

Сообщайте об уязвимостях **закрыто**: Security → *Report a vulnerability* на
https://github.com/igormel81/gene_archive (закрытые сообщения GitHub). Не открывайте публичный issue.
Особенно важны: утечки сведений о живых людях или скрытых документов на собранный сайт, в data.json
или GEDCOM; сервер комментариев (`gene_archive/server.py`); онлайн-редактор (`gene_archive/editor.py`: вход, сессии, CSRF, загрузка файлов, роли); выход за пределы папки сайта; обход PIN.
