# Runbook: deploy Slip & Score to ceramics.mauriecloud.com

```
phone / Mac ─HTTPS─▶ Cloudflare (Access login) ─▶ cloudflared ─▶ nginx 127.0.0.1:8090 ─▶ gunicorn 127.0.0.1:8002
                                                                   ├─ /static/ → staticfiles/
                                                                   └─ /media/  → media/
```

This reuses infrastructure already on the server from the first app
(meal-planner): nginx on `127.0.0.1:8090` with a `default_server` that drops
unknown hosts, the armhf `server_names_hash_bucket_size` fix, the Cloudflare
Tunnel, and the Zero Trust One-time PIN login method. If you're starting on a
fresh machine, set those up first (see the comments in
`deploy/nginx-slip-and-score.conf`).

Two locks on the door: **Cloudflare Access** in front of the whole hostname,
and **Django login** on every page (`LoginRequiredMiddleware`). Set up Access
(step 4) **before** the tunnel route (step 7).

All commands run on the **server** (`ssh` in) unless noted.

---

## 0. Check

```bash
sudo ss -tlnp | grep -E ':(8002|8090)\b'   # 8002 free; 8090 = nginx
ls /etc/nginx/conf.d/                        # server-names-hash.conf present
sudo cat /etc/cloudflared/config.yml         # locally managed tunnel, existing ingress
free -h
```

## 1. Get the code

```bash
cd ~/Projects
git clone git@github.com:<you>/slip-and-score.git
cd slip-and-score
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Optional HEIC support (only if `pillow-heif` installs on your platform —
not guaranteed on 32-bit ARM; iOS usually sends JPEG anyway):

```bash
venv/bin/pip install pillow-heif || echo "skip HEIC — JPEG uploads still work"
```

## 2. Environment file

```bash
cp deploy/slip-and-score.env.example .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
nano .env                     # paste the key into DJANGO_SECRET_KEY
set -a; . ./.env; set +a
venv/bin/python manage.py check --deploy
```

Expect exactly two warnings — W004 (HSTS) and W008 (SSL redirect). Cloudflare
does both.

## 3. Database and logins

```bash
set -a; . ./.env; set +a
venv/bin/python manage.py migrate
venv/bin/python manage.py createsuperuser     # one per person who'll use the site
```

Everyone who edits glazes, clay bodies or piece details uses `/admin/`, so
make each person a superuser (it's a household app). Use a password manager;
the session lasts 90 days so you won't type it often.

## 4. Cloudflare Access (dashboard) — before step 7

Zero Trust → **Access controls → Applications → Add an application → Self-hosted**:

| Setting | Value |
|---|---|
| Public hostname | `ceramics` . `mauriecloud.com`, path empty |
| Access policy | reuse the existing household policy (**Add existing policy**) |
| Identity providers | turn off "Accept all", select **One-time PIN** only |
| Instant authentication | on |
| Name | `slip-and-score` |

The One-time PIN identity provider must already exist (Integrations →
Identity providers); it does if the first app was set up with it.

## 5. Service

```bash
sudo cp deploy/slip-and-score.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now slip-and-score
systemctl status slip-and-score --no-pager
journalctl -u slip-and-score -n 30 --no-pager
curl -sI -H 'Host: ceramics.mauriecloud.com' -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8002/ | grep -iE '^(HTTP|location)'
# Expect 302 → /accounts/login/?next=/   (Django login required)
```

## 6. nginx

```bash
sudo cp deploy/nginx-slip-and-score.conf /etc/nginx/sites-available/slip-and-score
sudo ln -s /etc/nginx/sites-available/slip-and-score /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

H='Host: ceramics.mauriecloud.com'
curl -s -o /dev/null -w "%{http_code} login\n"  -H "$H" http://127.0.0.1:8090/accounts/login/
curl -s -o /dev/null -w "%{http_code} css\n"    -H "$H" http://127.0.0.1:8090/static/studio/style.css
curl -s -o /dev/null -w "%{http_code} icon\n"   -H "$H" http://127.0.0.1:8090/static/studio/icon-180.png
# Expect 200 ×3. (Media can only be checked after the first upload.)
```

If nginx can't read files under your home directory (403 in the error log),
check `namei -l /home/pi/Projects/slip-and-score/staticfiles`; on a fresh Debian
12+/Trixie install the home dir is 0700 and needs
`sudo setfacl -m u:www-data:x /home/pi /home/pi/Projects`.

## 7. Tunnel route

Add above the `http_status:404` catch-all in `/etc/cloudflared/config.yml`
(and in `~/.cloudflared/config.yml` if you keep a copy there):

```yaml
  - hostname: ceramics.mauriecloud.com
    service: http://localhost:8090
```

```bash
sudo cp /etc/cloudflared/config.yml ~/Backup/cloudflared-config.yml.$(date +%F)
sudo nano /etc/cloudflared/config.yml
# `--config` goes BEFORE `ingress` on cloudflared 2026.x
sudo cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate
cloudflared tunnel --config /etc/cloudflared/config.yml ingress rule https://ceramics.mauriecloud.com/
# route dns runs as your user, not sudo — cert.pem lives in ~/.cloudflared
cloudflared tunnel route dns <tunnel-id> ceramics.mauriecloud.com
sudo systemctl restart cloudflared

curl -sI https://ceramics.mauriecloud.com/ | grep -iE '^(HTTP|location)'
# Expect 302 → <team>.cloudflareaccess.com — NOT a 200 or a Django login page.
```

## 8. Test (phone first)

- [ ] Private window → Cloudflare email-code login → Django login → home
- [ ] **＋ Add** on the phone: new piece, stage, take 2 photos → saved, lands on the piece timeline
- [ ] Photos show (thumbnails and full size) → `/media/` works through nginx
- [ ] Home shows the entry under **Needs notes** → tap → write notes → it leaves the list
- [ ] Add again to the same piece + stage the same day → photos join the same entry
- [ ] `/admin/` → add a glaze and a clay body; link the glaze to the piece
- [ ] Glazes → the glaze → upload a test tile photo
- [ ] Share → **Add to Home Screen** → opens full-screen with the pot icon
- [ ] `journalctl -u slip-and-score` and `/var/log/nginx/slip-and-score.error.log` clean

## Deploying changes

```bash
cd ~/Projects/slip-and-score && git pull && venv/bin/pip install -r requirements.txt && sudo systemctl restart slip-and-score
```

## Backups

Back up `db.sqlite3` (consistently: `sqlite3 db.sqlite3 ".backup '/path/db-$(date +%F).sqlite3'"`)
and `media/`. The photos are irreplaceable.

## Rollback

```bash
sudo systemctl disable --now slip-and-score
sudo rm /etc/nginx/sites-enabled/slip-and-score && sudo systemctl reload nginx
# remove the ceramics.mauriecloud.com ingress entry, restart cloudflared
```
