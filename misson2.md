###  Exercise 4.1: API Key authentication

```bash
cd ../../04-api-gateway/develop
```

**Nhiệm vụ:** Đọc `app.py` và tìm:
- API key được check ở đâu?
- Điều gì xảy ra nếu sai key?
- Làm sao rotate key?

Test:
```bash
python app.py

#  Không có key
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'

#  Có key
curl http://localhost:8000/ask -X POST \
  -H "X-API-Key: secret-key-123" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

###  Exercise 4.2: JWT authentication (Advanced)

```bash
cd ../production
```

**Nhiệm vụ:** 
1. Đọc `auth.py` — hiểu JWT flow
2. Lấy token:
```bash
python app.py

curl http://localhost:8000/token -X POST \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "secret"}'
```

3. Dùng token để gọi API:
```bash
TOKEN="<token_từ_bước_2>"
curl http://localhost:8000/ask -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain JWT"}'
```

###  Exercise 4.3: Rate limiting

**Nhiệm vụ:** Đọc `rate_limiter.py` và trả lời:
- Algorithm nào được dùng? (Token bucket? Sliding window?)
- Limit là bao nhiêu requests/minute?
- Làm sao bypass limit cho admin?

Test:
```bash
# Gọi liên tục 20 lần
for i in {1..20}; do
  curl http://localhost:8000/ask -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"question": "Test '$i'"}'
  echo ""
done
```

Quan sát response khi hit limit.

###  Exercise 4.4: Cost guard

**Nhiệm vụ:** Đọc `cost_guard.py` và implement logic:

```python
def check_budget(user_id: str, estimated_cost: float) -> bool:
    """
    Return True nếu còn budget, False nếu vượt.
    
    Logic:
    - Mỗi user có budget $10/tháng
    - Track spending trong Redis
    - Reset đầu tháng
    """
    # TODO: Implement
    pass
```

<details>
<summary> Solution</summary>

```python
import redis
from datetime import datetime

r = redis.Redis()

def check_budget(user_id: str, estimated_cost: float) -> bool:
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"
    
    current = float(r.get(key) or 0)
    if current + estimated_cost > 10:
        return False
    
    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)  # 32 days
    return True
```

</details>

###  Checkpoint 4

- [ ] Implement API key authentication
- [ ] Hiểu JWT flow
- [ ] Implement rate limiting
- [ ] Implement cost guard với Redis

---

## Part 5: Scaling & Reliability (40 phút)

###  Concepts

**Vấn đề:** 1 instance không đủ khi có nhiều users.

**Giải pháp:**
1. **Stateless design** — Không lưu state trong memory
2. **Health checks** — Platform biết khi nào restart
3. **Graceful shutdown** — Hoàn thành requests trước khi tắt
4. **Load balancing** — Phân tán traffic

###  Exercise 5.1: Health checks

```bash
cd ../../05-scaling-reliability/develop
```

**Nhiệm vụ:** Implement 2 endpoints:

```python
@app.get("/health")
def health():
    """Liveness probe — container còn sống không?"""
    # TODO: Return 200 nếu process OK
    pass

@app.get("/ready")
def ready():
    """Readiness probe — sẵn sàng nhận traffic không?"""
    # TODO: Check database connection, Redis, etc.
    # Return 200 nếu OK, 503 nếu chưa ready
    pass
```

<details>
<summary> Solution</summary>

```python
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    try:
        # Check Redis
        r.ping()
        # Check database
        db.execute("SELECT 1")
        return {"status": "ready"}
    except:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready"}
        )
```

</details>

###  Exercise 5.2: Graceful shutdown

**Nhiệm vụ:** Implement signal handler:

```python
import signal
import sys

def shutdown_handler(signum, frame):
    """Handle SIGTERM from container orchestrator"""
    # TODO:
    # 1. Stop accepting new requests
    # 2. Finish current requests
    # 3. Close connections
    # 4. Exit
    pass

signal.signal(signal.SIGTERM, shutdown_handler)
```

Test:
```bash
python app.py &
PID=$!

# Gửi request
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Long task"}' &

# Ngay lập tức kill
kill -TERM $PID

# Quan sát: Request có hoàn thành không?
```

###  Exercise 5.3: Stateless design

```bash
cd ../production
```

**Nhiệm vụ:** Refactor code để stateless.

**Anti-pattern:**
```python
#  State trong memory
conversation_history = {}

@app.post("/ask")
def ask(user_id: str, question: str):
    history = conversation_history.get(user_id, [])
    # ...
```

**Correct:**
```python
#  State trong Redis
@app.post("/ask")
def ask(user_id: str, question: str):
    history = r.lrange(f"history:{user_id}", 0, -1)
    # ...
```

Tại sao? Vì khi scale ra nhiều instances, mỗi instance có memory riêng.

###  Exercise 5.4: Load balancing

**Nhiệm vụ:** Chạy stack với Nginx load balancer:

```bash
docker compose up --scale agent=3
```

Quan sát:
- 3 agent instances được start
- Nginx phân tán requests
- Nếu 1 instance die, traffic chuyển sang instances khác

Test:
```bash
# Gọi 10 requests
for i in {1..10}; do
  curl http://localhost/ask -X POST \
    -H "Content-Type: application/json" \
    -d '{"question": "Request '$i'"}'
done

# Check logs — requests được phân tán
docker compose logs agent
```

###  Exercise 5.5: Test stateless

```bash
python test_stateless.py
```

Script này:
1. Gọi API để tạo conversation
2. Kill random instance
3. Gọi tiếp — conversation vẫn còn không?

###  Checkpoint 5

- [ ] Implement health và readiness checks
- [ ] Implement graceful shutdown
- [ ] Refactor code thành stateless
- [ ] Hiểu load balancing với Nginx
- [ ] Test stateless design



# Question #

## Part 4: API Security

### Exercise 4.1-4.3: Test results

**Exercise 4.1 — API Key Authentication**

API key được check ở `verify_api_key()` trong `04-api-gateway/develop/app.py` (line 39-54).
Dependency này được inject vào `/ask` endpoint qua `Depends(verify_api_key)`.

Test output (không có key → 401):
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

Để rotate key: thay đổi biến môi trường `AGENT_API_KEY` và restart server — không cần sửa code.

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

---

### Exercise 4.4: Cost guard implementation

**Approach:**

`CostGuard` class trong `cost_guard.py` bảo vệ budget theo 2 tầng:

1. **Per-user daily budget ($1/ngày):** Mỗi user được track riêng qua `UsageRecord`. Khi `total_cost_usd >= daily_budget_usd` → raise `402 Payment Required`.

2. **Global daily budget ($10/ngày):** Tổng cost của tất cả users. Khi vượt → raise `503 Service Unavailable`.

3. **Warning at 80%:** Log warning khi user dùng 80% budget để theo dõi.

**Flow:**
```
Request → check_budget() → gọi LLM → record_usage() → trả response
```

**Cải tiến cho production:** Thay in-memory dict bằng Redis với key `budget:{user_id}:{YYYY-MM}` để scale nhiều instances (như solution trong file):
```python
key = f"budget:{user_id}:{month_key}"
current = float(r.get(key) or 0)
if current + estimated_cost > 10:
    return False
r.incrbyfloat(key, estimated_cost)
r.expire(key, 32 * 24 * 3600)
```

---

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