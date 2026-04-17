#  Delivery Checklist — Day 12 Lab Submission

> **Student Name:** Nguyễn Tùng Lâm 
> **Student ID:** 2A202600410  
> **Date:** 17/4/2026

---

##  Submission Requirements

Submit a **GitHub repository** containing:

### 1. Mission Answers (40 points)

Create a file `MISSION_ANSWERS.md` with your answers to all exercises:

```markdown
# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
1. Vấn đề 1: API key hardcode trong code
2. Vấn đề 2: Không có config management
3. Vấn đề 3: Print thay vì proper logging
4. Vấn đề 4: Không có health check endpoint
5. Vấn đề 5: Port cố định — không đọc từ environment

...

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Why Important? |
|---------|-------------------|------------|-------------------|
| Config | Hardcode (OPENAI_API_KEY = "sk-...", port=8000) | Env vars qua settings objectvars | Hardcode lộ secret khi push GitHub; env vars → thay đổi config mà không cần sửa code |
| Health check | 	Không có  | Có /health (liveness) + /ready (readiness) | Platform cloud cần endpoint này để biết container còn sống không → tự động restart khi crash |
| Logging | print() — log cả secret ra ngoài | JSON structured logging, không log secret | JSON dễ parse bởi log aggregator (Datadog, Loki); print() không có level, không filter được |
| Shutdown | Đột ngột — không xử lý SIGTERM | Graceful — bắt SIGTERM, hoàn thành request đang chạy rồi mới tắt | Tắt đột ngột → request dang dở bị lỗi; graceful → zero downtime khi deploy/scale |

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. Base image: FROM python:3.11
2. Working directory: day12_ha-tang-cloud_va_deployment\02-docker\develop/app
3. Tại sao COPY requirements.txt trước :
Docker invalidate cache của một layer khi layer phía trên nó thay đổi. Code thay đổi thường xuyên, requirements.txt thay đổi hiếm → để requirements lên trước để pip install được cache lại.
4. CMD vs ENTRYPOINT khác nhau thế nào :
|  | Override được?|	Dùng khi nào |
|---------|---------|------------|
CMD| Có |	Script đơn giản, tool linh hoạt |
ENTRYPOINT|	Không  (chỉ --entrypoint flag) |	Container như một executable cố định |

### Exercise 2.3: Image size comparison
- Develop: 424 MB
- Production: 56.6MB MB
- Difference: 86.65% smaller

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- URL: curl https://testexample-production.up.railway.app/
- Screenshot: 

## Part 4: API Security

### Exercise 4.1-4.3: Test results
test output (không có key → 401):
```
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

Test output (sai key → 403):
```
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}
```

Test output (đúng key → 200):
```json
{
  "question": "Hello",
  "answer": "Mock response for: Hello"
}
```

**Exercise 4.2 — JWT Flow**

1. POST `/token` với username/password → nhận JWT token
2. Dùng token trong header `Authorization: Bearer <token>` để gọi `/ask`
3. Server decode token, verify signature, extract user info

**Exercise 4.3 — Rate Limiting**

- **Algorithm:** Sliding Window Counter (dùng deque lưu timestamps)
- **Limit:** User thường: 10 req/phút | Admin: 100 req/phút
- **Bypass cho admin:** Dùng `rate_limiter_admin` instance thay vì `rate_limiter_user`

Khi hit limit → 429 Too Many Requests:
```json
{
  "error": "Rate limit exceeded",
  "limit": 10,
  "window_seconds": 60,
  "retry_after_seconds": 45
}
```

### Exercise 4.4: Cost guard implementation
**Approach:**

`CostGuard` class trong `cost_guard.py` bảo vệ budget theo 2 tầng:

1. **Per-user daily budget ($1/ngày):** Mỗi user được track riêng qua `UsageRecord`. Khi `total_cost_usd >= daily_budget_usd` → raise `402 Payment Required`.

2. **Global daily budget ($10/ngày):** Tổng cost của tất cả users. Khi vượt → raise `503 Service Unavailable`.

3. **Warning at 80%:** Log warning khi user dùng 80% budget để theo dõi.

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes
**Exercise 5.1 — Health Checks**

```python
@app.get("/health")
def health():
    return {"status": "ok"}  # Liveness: process còn sống

@app.get("/ready")
def ready():
    try:
        r.ping()           # Check Redis
        db.execute("SELECT 1")  # Check DB
        return {"status": "ready"}
    except:
        return JSONResponse(status_code=503, content={"status": "not ready"})
```

`/health` = liveness probe (container còn chạy không?)
`/ready` = readiness probe (sẵn sàng nhận traffic chưa?)

**Exercise 5.2 — Graceful Shutdown**

```python
def shutdown_handler(signum, frame):
    server.should_exit = True  # Stop accepting new requests
    # Uvicorn tự hoàn thành requests đang chạy trước khi exit
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
```

Khi Kubernetes gửi SIGTERM, server hoàn thành request hiện tại rồi mới tắt — không drop request giữa chừng.

**Exercise 5.3 — Stateless Design**

Anti-pattern: lưu `conversation_history` trong memory → mỗi instance có state riêng, scale ra sẽ mất context.

Correct: lưu trong Redis → tất cả instances đều đọc/ghi cùng 1 nơi:
```python
history = r.lrange(f"history:{user_id}", 0, -1)
r.rpush(f"history:{user_id}", new_message)
```

**Exercise 5.4 — Load Balancing**

```bash
docker compose up --scale agent=3
```

Nginx phân tán traffic theo round-robin giữa 3 agent instances. Nếu 1 instance crash, health check phát hiện và Nginx tự loại khỏi pool.

**Exercise 5.5 — Test Stateless**

`test_stateless.py` verify:
1. Tạo conversation trên instance A
2. Kill instance A
3. Tiếp tục conversation → vẫn hoạt động vì history trong Redis, không phải memory của instance A

---

### 2. Full Source Code - Lab 06 Complete (60 points)

Your final production-ready agent with all files:

```
your-repo/
├── app/
│   ├── main.py              # Main application
│   ├── config.py            # Configuration
│   ├── auth.py              # Authentication
│   ├── rate_limiter.py      # Rate limiting
│   └── cost_guard.py        # Cost protection
├── utils/
│   └── mock_llm.py          # Mock LLM (provided)
├── Dockerfile               # Multi-stage build
├── docker-compose.yml       # Full stack
├── requirements.txt         # Dependencies
├── .env.example             # Environment template
├── .dockerignore            # Docker ignore
├── railway.toml             # Railway config (or render.yaml)
└── README.md                # Setup instructions
```

**Requirements:**
-  All code runs without errors
-  Multi-stage Dockerfile (image < 500 MB)
-  API key authentication
-  Rate limiting (10 req/min)
-  Cost guard ($10/month)
-  Health + readiness checks
-  Graceful shutdown
-  Stateless design (Redis)
-  No hardcoded secrets

---

### 3. Service Domain Link

Create a file `DEPLOYMENT.md` with your deployed service information:

```markdown
# Deployment Information

## Public URL
https://your-agent.railway.app

## Platform
Railway / Render / Cloud Run

## Test Commands

### Health Check
```bash
curl https://your-agent.railway.app/health
# Expected: {"status": "ok"}
```

### API Test (with authentication)
```bash
curl -X POST https://your-agent.railway.app/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

## Environment Variables Set
- PORT
- REDIS_URL
- AGENT_API_KEY
- LOG_LEVEL

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
```

##  Pre-Submission Checklist

- [ ] Repository is public (or instructor has access)
- [ ] `MISSION_ANSWERS.md` completed with all exercises
- [ ] `DEPLOYMENT.md` has working public URL
- [ ] All source code in `app/` directory
- [ ] `README.md` has clear setup instructions
- [ ] No `.env` file committed (only `.env.example`)
- [ ] No hardcoded secrets in code
- [ ] Public URL is accessible and working
- [ ] Screenshots included in `screenshots/` folder
- [ ] Repository has clear commit history

---

##  Self-Test

Before submitting, verify your deployment:

```bash
# 1. Health check
curl https://your-app.railway.app/health

# 2. Authentication required
curl https://your-app.railway.app/ask
# Should return 401

# 3. With API key works
curl -H "X-API-Key: YOUR_KEY" https://your-app.railway.app/ask \
  -X POST -d '{"user_id":"test","question":"Hello"}'
# Should return 200

# 4. Rate limiting
for i in {1..15}; do 
  curl -H "X-API-Key: YOUR_KEY" https://your-app.railway.app/ask \
    -X POST -d '{"user_id":"test","question":"test"}'; 
done
# Should eventually return 429
```

---

##  Submission

**Submit your GitHub repository URL:**

```
https://github.com/your-username/day12-agent-deployment
```

**Deadline:** 17/4/2026

---

##  Quick Tips

1.  Test your public URL from a different device
2.  Make sure repository is public or instructor has access
3.  Include screenshots of working deployment
4.  Write clear commit messages
5.  Test all commands in DEPLOYMENT.md work
6.  No secrets in code or commit history

---

##  Need Help?

- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Review [CODE_LAB.md](CODE_LAB.md)
- Ask in office hours
- Post in discussion forum

---

**Good luck! **
