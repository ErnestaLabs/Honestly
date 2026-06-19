# Honestly — 1M User Go-Live Checklist

## Pre-Flight (VPS Setup)

- [ ] Docker & Docker Compose installed on VPS
- [ ] Domain pointed to VPS IP (`app.usehonestly.co.uk`, `usehonestly.co.uk`)
- [ ] `.env` file populated with real secrets (never commit this)
- [ ] Ports 80/443 open in firewall, 8000/5432/6379 **closed** to external

## 1. SSL / HTTPS (Required for Telegram Mini Apps)

```bash
# Option A: Certbot standalone (one-time)
docker run -it --rm -p 80:80 -v /etc/letsencrypt:/etc/letsencrypt certbot/certbot certonly --standalone -d app.usehonestly.co.uk

# Option B: Caddy reverse proxy (auto-renewing)
# Add a caddy service to docker-compose.yml:
#   caddy:
#     image: caddy:alpine
#     ports: [80:80, 443:443]
#     volumes: [./Caddyfile:/etc/caddy/Caddyfile]
#
# Caddyfile:
#   app.usehonestly.co.uk { reverse_proxy frontend:80 }

# Update frontend/nginx.conf to listen on 443 and point to certs,
# OR put Caddy/Traefik in front of Nginx.
```

Minimal nginx SSL config snippet:
```nginx
server {
    listen 443 ssl http2;
    server_name app.usehonestly.co.uk;
    ssl_certificate     /etc/letsencrypt/live/app.usehonestly.co.uk/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.usehonestly.co.uk/privkey.pem;
    # ... rest of config from frontend/nginx.conf ...
}
server {
    listen 80;
    server_name app.usehonestly.co.uk;
    return 301 https://$host$request_uri;
}
```

## 2. Set Telegram Webhook

```bash
curl -F "url=https://app.usehonestly.co.uk/api/v1/webhook" \
     https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook

# Verify:
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo
```

## 3. Configure Mini App in BotFather

- Open @BotFather on Telegram
- `/newapp` — send App Name ("Honestly")
- Send HTTPS URL: `https://app.usehonestly.co.uk`
- Send short description (max 512 chars)
- Upload 640×360 splash image
- `/setmenubutton` — set Mini App button text ("Value a Property")

## 4. Database Seeding

```bash
# Start the stack
docker compose up -d db redis

# Wait for PostGIS to be healthy (~30s)
docker compose logs db

# Ingest HMLR bulk data (the ~153MB pp-2025.csv)
docker compose run --rm backend python graph_db.py init
docker compose run --rm backend python graph_db.py ingest-hmlr --file data/ppd.csv
# This takes ~3-5 minutes for 880K rows. For full 28M history,
# see graph_db.py CLI docs.

# Ingest EPC cache
docker compose run --rm backend python graph_db.py ingest-epc --file data/epc_public_cache.json

# Ingest geo data
docker compose run --rm backend python graph_db.py ingest-geo

# Compute postcode neighbours
docker compose run --rm backend python graph_db.py compute-neighbours

# Verify
docker compose run --rm backend python graph_db.py status
```

## 5. Verify the Full Stack

```bash
# Start everything
docker compose up -d

# Check all services healthy
docker compose ps

# Test health endpoint
curl http://localhost:8000/health
# → {"ok":true,"service":"honestly-api"}

# Test health via Nginx
curl http://localhost/health
# → {"ok":true,"service":"honestly-api"}

# Test a valuation
curl -X POST http://localhost/api/v1/properties/valuate \
  -H "Content-Type: application/json" \
  -d '{"address":"10 Downing Street, London SW1A 2AA","user_id":"test_user"}'

# Test the catalog
curl http://localhost/api/v1/products/catalog
```

## 6. Monitoring

```bash
# Docker logs (all services combined, follow)
docker compose logs -f

# Redis: check credit balances, leaderboard sizes
docker compose exec redis redis-cli DBSIZE

# Postgres: check row counts
docker compose exec db psql -U honestly -c "SELECT COUNT(*) FROM hmlr_sales;"
docker compose exec db psql -U honestly -c "SELECT COUNT(*) FROM postcodes;"

# Resource usage
docker stats
```

## 7. API Keys & Quotas (Pre-Launch)

- [ ] **Google Cloud Console** → Raise Maps/Street View/Solar API quotas
- [ ] **Google Cloud** → Set billing alerts ($50, $100, $500 thresholds)
- [ ] **OpenRouter** → Check credit balance, set auto-top-up
- [ ] **Telegram** → Bot token has no rate limit for payments, but `sendMessage` is ~30 msg/s. Use `sendMessage` with queue if needed.

## 8. Launch Sequence

```bash
# 1. Final git pull
git pull origin main

# 2. Rebuild with latest code
docker compose build --no-cache backend frontend

# 3. Restart without downtime (if using swarm or blue-green)
# For single-host: brief downtime okay
docker compose up -d

# 4. Verify webhook still registered
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo

# 5. Run smoke test
docker compose exec backend python launch_gate.py

# 6. Announce in @BotFather → publish Mini App
```

## 9. Post-Launch (First Hour)

- [ ] Monitor `docker compose logs backend` for 500s
- [ ] Watch Redis memory usage (`INFO memory`)
- [ ] Check Postgres connection count (`SELECT count(*) FROM pg_stat_activity`)
- [ ] Verify successful_payment webhooks arrive in logs
- [ ] Test a purchase end-to-end (subscribe → get credits → buy a product)

## 10. Scaling (Beyond 10K Concurrent)

- [ ] Add a Redis cluster or ElastiCache (remove `--save` for pure in-memory)
- [ ] Add a load balancer (Nginx upstream, HAProxy, or Cloudflare)
- [ ] Read-replica for PostGIS
- [ ] Move `graph_db` queries to the PostGIS database directly
- [ ] Horizontal scaling: multiple `backend` replicas behind the LB
- [ ] CDN for frontend assets (Cloudflare, Vercel, or S3+CloudFront)

---

**You've built a fortress. Now go get your million users.**
