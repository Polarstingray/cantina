# Phase 3 — Remote access via Cloudflare Tunnel

Lets the family reach Cantina from outside the LAN over `https://`, with no VPN
to toggle and no inbound ports opened on your router. cloudflared dials *out* to
Cloudflare's edge and forwards traffic down to uvicorn on `127.0.0.1:8000`.

You need a Cloudflare account and a domain managed by Cloudflare (a subdomain is
fine). Everything below is a one-time setup.

## 1. Install cloudflared

Debian/Ubuntu:

```bash
# Add Cloudflare's apt repo, then:
sudo apt-get update && sudo apt-get install -y cloudflared
cloudflared --version
```

(Or grab the static binary from Cloudflare's GitHub releases if you don't want
the repo.)

## 2. Authenticate and create the tunnel

```bash
cloudflared tunnel login                 # opens a browser; pick your domain
cloudflared tunnel create cantina        # prints a TUNNEL-UUID + writes creds
```

`create` writes the credentials file to `~/.cloudflared/<TUNNEL-UUID>.json`.

## 3. Fill in config.yml

Edit `config.yml` in this directory and replace:
- `<TUNNEL-UUID>` (appears twice — the `tunnel:` line and the credentials path)
- `cantina.example.com` → the public hostname you want

## 4. Route DNS to the tunnel

```bash
cloudflared tunnel route dns cantina cantina.example.com
```

This creates the proxied CNAME in Cloudflare so the hostname resolves to the
tunnel. (Use the same hostname you put in `config.yml`.)

## 5. Flip the app into "behind TLS" mode

The tunnel terminates TLS, so the app must now bind to localhost only and set
the secure-cookie / trusted-proxy flags. These are **pre-staged (commented out)**
in `../cantina.service` — uncomment them:

```ini
Environment=CANTINA_SECURE_COOKIES=1     # __Host- cookie, Secure, HSTS
Environment=CANTINA_TRUSTED_PROXY=1      # rate limiter reads CF-Connecting-IP
# switch ExecStart to bind loopback so the tunnel/LAN is the only way in:
ExecStart=.../venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000
```

Then reload + restart:

```bash
systemctl --user daemon-reload
systemctl --user restart cantina.service
```

> ⚠️ With `CANTINA_SECURE_COOKIES=1` the cookie is `Secure`-only, so it will
> **not** work over plain `http://` on the LAN anymore — access is through the
> `https://` hostname from then on. Everyone re-logs in once after the restart.

## 6. Start the tunnel

Either run it under systemd (recommended, survives logout if you enable
lingering) using the unit in this directory:

```bash
cp cantina-tunnel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cantina-tunnel.service
loginctl enable-linger "$USER"     # so it runs without an active login session
```

…or test it interactively first:

```bash
cloudflared tunnel --config ./config.yml run
```

## 7. Verify the cutover

From a browser on a *different* network (phone on cellular works), open
`https://cantina.example.com` and check:

- [ ] Login works and the app loads (no CSP violations in the console).
- [ ] The session cookie is `__Host-cantina_session`, `Secure`, `SameSite=Strict`
      (DevTools → Application → Cookies).
- [ ] Response headers include `Strict-Transport-Security` and the CSP.
- [ ] `curl -sI https://cantina.example.com/docs` → `404` (docs stay disabled).
- [ ] A handful of bad logins return `429` with `Retry-After`, and the IP shown
      in the app logs is the real client IP (not the tunnel's) — confirms
      `CANTINA_TRUSTED_PROXY` is wired through `CF-Connecting-IP`.

## Notes

- The tunnel is **outbound-only**: no port-forwarding, no firewall holes.
- The in-memory login throttle is per-process; that's fine for the single
  uvicorn worker the family uses. The public Phase 4 deploy will need a shared
  store (Redis) — see the roadmap.
- Optionally add Cloudflare Access in front of the hostname for an extra
  identity gate (email OTP / Google login) before requests even reach the app.
  Not required, since the app has its own auth, but it's a cheap second layer.
