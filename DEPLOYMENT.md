# Deployment Information

## Public URL
https://lab06-production.up.railway.app

## Platform
Railway

## Test Commands

### Health Check
```bash
curl https://lab06-production.up.railway.app/health
# Expected: {"status": "ok"}
```

### Readiness Check
```bash
curl https://lab06-production.up.railway.app/ready
# Expected: {"status": "ready"}
```

### No API Key → 401
```bash
curl -X POST https://lab06-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# Expected: 401 {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

### Wrong API Key → 403
```bash
curl -X POST https://lab06-production.up.railway.app/ask \
  -H "X-API-Key: wrong-key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# Expected: 403 {"detail":"Invalid API key."}
```

### API Test (with authentication)
```bash
curl -X POST https://lab06-production.up.railway.app/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# Expected: 200 {"question":"Hello","answer":"..."}
```

### Rate Limiting Test (hit 429 after 10 req/min)
```bash
for i in {1..15}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://lab06-production.up.railway.app/ask \
    -H "X-API-Key: $AGENT_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"user_id":"test","question":"test"}';
done
# Expected: first 10 → 200, then 429
```

## Environment Variables Set
| Variable | Description |
|---|---|
| `PORT` | Server port (Railway injects automatically) |
| `REDIS_URL` | Redis connection string (Railway Redis plugin) |
| `AGENT_API_KEY` | Secret key for X-API-Key header authentication |
| `JWT_SECRET` | Secret for JWT token signing |
| `ENVIRONMENT` | Set to `production` |
| `LOG_LEVEL` | `INFO` |
| `MONTHLY_BUDGET_USD` | Per-user monthly cost cap (default `10.0`) |
| `RATE_LIMIT_PER_MINUTE` | Request rate cap per user (default `10`) |

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)