# Slip & Score

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Django](https://img.shields.io/badge/django-5.2-0C4B33)
![License: MIT](https://img.shields.io/badge/license-MIT-yellow)
![Self-hosted](https://img.shields.io/badge/self--hosted-Raspberry%20Pi-c51a4a)

*Slip and score: roughen both surfaces, add slip, press together — how potters join two pieces of clay. This app joins the photos and the notes.*

A studio journal for a home potter: follow each piece from lump of clay to
finished pot, keep a glaze library with test tiles, and see which glazes
ended up on which pieces.

Built around how studio work actually goes: **hands are covered in clay
during a session, clean afterwards.** So adding is photo + stage, nothing
else, and the writing happens later.

## What it does

- **Quick add from the phone.** Pick the piece (or name a new one), tap the
  stage, take or choose photos, save. The stage defaults to whatever usually
  comes next for that piece.
- **One session, one entry.** Everything added to the same piece and stage on
  the same day lands in a single journal entry.
- **Needs-notes queue.** The home page lists recent entries with photos but no
  notes yet — write them up once your hands are clean.
- **Piece timelines.** Thrown → trimmed → leather-hard → bone dry → bisqued →
  glazed → glaze fired → finished (or "didn't make it"), with photos at each step.
- **Glaze library.** Maker, cone range, surface, food safety, recipe, a link to
  Glazy or the maker, test-tile photos, and every piece the glaze was used on.
- **Phone photos handled properly.** Rotation fixed, resized to a 2000px display
  copy plus a thumbnail, shoot time kept from EXIF, all other EXIF (including
  GPS location) stripped. Files get random names. HEIC works if `pillow-heif`
  is installed.
- **Add to Home Screen.** Web app manifest and icon, so it opens like an app.

Django's admin handles the rest: glaze and clay body details, which glazes
went on which piece (layer, coats, application method).

## Running it locally

```bash
git clone https://github.com/mbulkeley/slip-and-score.git
cd slip-and-score
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python manage.py migrate
venv/bin/python manage.py createsuperuser
venv/bin/python manage.py runserver
```

Open `http://127.0.0.1:8000/` and log in. Every page requires a login.

Run the tests with `venv/bin/python manage.py test`.

## Deploying

The reference deployment is a Raspberry Pi:

```
Cloudflare (HTTPS + Access) → cloudflared tunnel → nginx (static/media) → gunicorn → Django
```

Everything is in [`deploy/`](deploy/): a systemd unit, an nginx site, an env
template and a step-by-step [`RUNBOOK.md`](deploy/RUNBOOK.md). Production
settings come from environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev placeholder | Required when `DJANGO_DEBUG=false` |
| `DJANGO_DEBUG` | `true` | Set `false` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | — | e.g. `https://ceramics.example.com` |
| `DJANGO_BEHIND_PROXY` | `false` | Trust `X-Forwarded-Proto` from the proxy |
| `DJANGO_SECURE_COOKIES` | `not DEBUG` | HTTPS-only cookies |
| `DJANGO_TIME_ZONE` | `Europe/Amsterdam` | Journal dates |
| `DJANGO_LOG_LEVEL` | `WARNING` | Django log level (stderr / journald) |

## Roadmap

- Glaze recipes with a batch calculator; layering matrix of test tiles
- QR stickers for glaze buckets and test tiles
- Firing log, shrinkage calculator, before/after slider
- Public gallery of finished pieces (`Project.is_public` and random photo
  names are already in place for it)

## License

MIT — see [LICENSE](LICENSE).
