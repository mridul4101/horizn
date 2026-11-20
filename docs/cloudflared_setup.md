# Cloudflared Setup Guide

Horizn uses [cloudflared](https://github.com/cloudflare/cloudflared) to create a **Quick Tunnel** — a temporary public HTTPS URL that lets the Meta Graph API reach your local machine during the carousel upload flow. No Cloudflare account is required.

---

## 1. Install cloudflared

```bash
brew install cloudflared
```

Verify the installation:

```bash
cloudflared --version
# cloudflared version 2024.x.x
```

---

## 2. How Quick Tunnels Work

When Horizn needs to upload images to Instagram, it temporarily exposes the local `/static` endpoint (served from `./data/exports`) to the internet via a Quick Tunnel:

```
https://<random-id>.trycloudflare.com  →  http://127.0.0.1:8000/static
```

- The tunnel is **ephemeral**: it starts when a publish job begins and is torn down immediately after.
- **No Cloudflare account or login** is required for Quick Tunnels.
- The random subdomain changes each time, which is handled automatically by Horizn's `publisher/tunnel.py`.

---

## 3. How Horizn Manages the Tunnel

You do not need to run `cloudflared` manually. Horizn's publisher module:

1. Spawns `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:{API_PORT}` as a subprocess.
2. Parses the assigned public URL from cloudflared's log output.
3. Passes that URL to the Meta Graph API as the `image_url` for each slide container.
4. Tears down the subprocess once all media containers are created.

---

## 4. Firewall / VPN Notes

- Quick Tunnels require **outbound HTTPS (port 443)** to `trycloudflare.com`. Most home and office networks allow this by default.
- If you are on a strict corporate VPN that blocks outbound connections, you may need to disconnect during publishing or configure a split-tunnel exception for `*.trycloudflare.com`.

---

## 5. Optional: Persistent Named Tunnel (Advanced)

If you prefer a stable subdomain (e.g., `horizn.yourdomain.com`), you can create a **Named Tunnel** with a free Cloudflare account:

```bash
cloudflared login
cloudflared tunnel create horizn
cloudflared tunnel route dns horizn horizn.yourdomain.com
```

Then update `publisher/tunnel.py` to use the named tunnel config instead of the Quick Tunnel flag. This is entirely optional and not required for normal use.
