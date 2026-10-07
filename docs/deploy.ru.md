# Публикация сайта

**[English version](deploy.md)**

`gene build my-family` кладёт готовый статический сайт в `my-family/_site`. Как выложить его
в интернет, зависит от того, нужны ли комментарии родственников.

| | Статический хостинг | Свой сервер |
|---|---|---|
| Стоимость | бесплатно (GitHub Pages, Netlify, Cloudflare Pages) | небольшой VPS |
| Комментарии родственников | нет | да, с модерацией |
| Закрытый архив по PIN | нет | да |
| `site.json` | `"comments": false` | `"comments": true` |

## Перед публикацией: приватность

- Собранный сайт скрывает живых, но **ваш `family_tree.json` — нет**. Никогда не публикуйте саму
  папку сайта (и открытый репозиторий с ней) — только собранную `_site`.
- Посмотрите вывод `gene build`: «живых — N, сведения скрыты». Откройте на собранном сайте
  нескольких живых родственников: видно должно быть только имя.
- Спросите родных, прежде чем публиковать их фотографии и истории; документы, которые просят
  убрать, отметьте `"hidden": true` — см. [руководство по поиску](research-guide.ru.md#8-этика-и-приватность).

## GitHub Pages

**А. Выложить собранный сайт** (проще всего, данные остаются у вас):

1. Создайте репозиторий, например `family-site`. Settings → Pages → Source: *Deploy from a branch*, `main`, `/ (root)`.
2. `gene build my-family --base-url https://<user>.github.io/family-site/`
3. Скопируйте содержимое `my-family/_site` в репозиторий и отправьте (push).

**Б. Собирать на GitHub** (данные — в **закрытом** репозитории; GitHub Pages из закрытого
репозитория — на платном тарифе): скопируйте [`templates/github-pages.yml`](../templates/github-pages.yml)
в `.github/workflows/site.yml` репозитория с вашим сайтом, затем Settings → Pages →
Source: *GitHub Actions*. Каждый push пересобирает и публикует сайт.

## Netlify, Cloudflare Pages, любой веб-сервер

Загрузите содержимое `_site` (в Netlify — перетаскиванием, на сервер — `rsync`). Для nginx или
Apache настройка не нужна: сайт — обычные файлы с относительными ссылками, работает и в подпапке.

## Свой сервер с комментариями

Сервер комментариев входит в пакет, ему нужен только Python:

```sh
gene serve my-family --host 127.0.0.1 --port 8111
```

Он собирает сайт, отдаёт его и хранит комментарии в `my-family/.gene-state/comments.db`.
Поставьте перед ним веб-сервер с HTTPS (Caddy, nginx) и задайте `GENE_TRUST_PROXY=1`, чтобы
ограничения видели настоящие адреса посетителей.

Caddy:

```
family.example.org {
    reverse_proxy 127.0.0.1:8111
}
```

nginx, сайт в подпапке:

```
location /family/ {
    proxy_pass http://127.0.0.1:8111/;
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

и `gene serve my-family --prefix /family`.

Служба systemd (`/etc/systemd/system/gene.service`):

```ini
[Unit]
Description=Family archive
After=network.target

[Service]
User=gene
WorkingDirectory=/srv/my-family
Environment=GENE_TRUST_PROXY=1
ExecStart=/usr/local/bin/gene serve /srv/my-family --host 127.0.0.1 --port 8111
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Docker

```sh
docker run -d -p 127.0.0.1:8111:8111 -v "$PWD/my-family:/site:ro" -v gene-state:/state ghcr.io/igormel81/gene_archive:latest
```

(или соберите образ сами: `docker build -t gene-archive .`)

или `docker compose up -d` с [`docker-compose.yml`](../docker-compose.yml). После правки данных
перезапустите контейнер — при старте он пересобирает сайт.

### Параметры

| Ключ `gene serve` | Переменная | Что значит |
|---|---|---|
| `--pin 1234` | `GENE_PIN` | сайт открывается только после ввода PIN (закрытый архив; страницы `noindex`) |
| `--moderate` | `GENE_MODERATE=1` | новые комментарии скрыты, пока вы их не одобрите |
| `--prefix /family` | `GENE_PREFIX` | путь сайта, если он в подпапке за прокси |
| `--state ПАПКА` | `GENE_STATE_DIR` | где лежит `comments.db` |
| — | `GENE_TRUST_PROXY=1` | брать адрес посетителя из `X-Forwarded-For` (только за своим прокси) |

### Комментарии

```sh
gene comments my-family list                        # все комментарии
gene comments my-family approve 12                  # опубликовать ожидающий проверки
gene comments my-family hide 13                     # скрыть спам
gene comments my-family done 12 "внесено в древо"   # «✓ Учтено» под комментарием
```

Комментарий — до 4000 знаков, не больше 30 за 10 минут с одного адреса; скрытое поле формы
отсеивает простых ботов. Делайте резервную копию `comments.db` вместе с данными.

## Релизы (для сопровождающих)

```sh
# поднимите версию в pyproject.toml, перенесите «Unreleased» из CHANGELOG под новую версию, закоммитьте, затем:
git tag v0.2.0 && git push origin v0.2.0
```

Workflow `Release` проверяет, что тег совпадает с версией в `pyproject.toml`, прогоняет тесты, создаёт
релиз на GitHub с разделом CHANGELOG и файлами пакета и публикует Docker-образ
`ghcr.io/igormel81/gene_archive:<версия>` (и `:latest`).

Публикация на PyPI выключена, пока её один раз не настроить:
1. На pypi.org → *Your projects* → *Publishing* → добавьте pending trusted publisher: проект `gene-archive`,
   владелец `igormel81`, репозиторий `gene_archive`, workflow `release.yml`, environment `pypi`.
2. На GitHub → Settings → Environments → создайте `pypi`; Settings → Secrets and variables → Actions →
   *Variables* → `PYPI_PUBLISH` = `true`.
Со следующим тегом пакет опубликуется и на PyPI, и заработает `pip install gene-archive`.
