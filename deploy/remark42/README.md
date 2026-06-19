# Blog comments - Remark42 (self-hosted)

[Remark42](https://github.com/umputun/remark42) - self-hosted, open-source (MIT). Runs under
`usehonestly.co.uk/remark42/` — no separate domain, no new DNS record, no new TLS cert. One
extra `location` block in the existing nginx config, that's it.

The blog only renders the widget once `REMARK_URL` is set in `/opt/honestly/.env`.

## Stand-up

**1. Storage dir** (on the VPS, once)

    mkdir -p /opt/honestly/deploy/remark42/var/db /opt/honestly/deploy/remark42/var/backup
    chown -R 1001:1001 /opt/honestly/deploy/remark42/var

**2. Start the container**

    cd /opt/honestly/deploy/remark42
    docker compose up -d
    docker compose logs -f remark42    # should show "starting server on :8080"

**3. nginx** — add inside the existing `usehonestly.co.uk` server block:

    location /remark42/ {
        proxy_pass         http://127.0.0.1:8081/;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

Then `nginx -t && systemctl reload nginx`.

**4. Wire the blog**

Add to `/opt/honestly/.env`:

    REMARK_URL=https://usehonestly.co.uk/remark42
    REMARK_SITE=honestly

Then rebuild:

    systemctl restart honestly-blog.service

## Telegram login

Uses `@usehonestly_comments_bot` — a dedicated bot separate from the live `@usehonestly_bot`,
so its `getUpdates` poller in `bot.py` is completely untouched.

## Moderation

Set `ADMIN_SHARED_ID` (your Telegram numeric id) in `.env` to get delete/block/pin controls
inside the widget.
