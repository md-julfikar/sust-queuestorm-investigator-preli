# RUNBOOK — QueueStorm Investigator

This runbook explains how to start, test, and verify the QueueStorm Investigator API locally or through Docker.

---

## 1. Requirements

- Python 3.10+
- pip
- Optional: Docker
- Optional: Gemini API key for LLM-polished text generation

The service works without a Gemini API key using local heuristic mode.

---

## 2. Environment Variables

Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

Available variables:

```env
HOST=0.0.0.0
PORT=8000
DEBUG=False
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
REQUEST_TIMEOUT_SEC=15.0
```

`GEMINI_API_KEY` is optional. Keep it empty to run local heuristic mode.

Do not commit `.env` or real API keys.

---

## 3. Local Run

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

The service starts at:

```txt
http://localhost:8000
```

---

## 4. Health Check

```bash
curl http://localhost:8000/health
```

Expected:

```json
{
  "status": "ok"
}
```

---

## 5. Analyze Ticket

```bash
curl -X POST http://localhost:8000/analyze-ticket \
  -H "Content-Type: application/json" \
  --data-binary @sample_request.json
```

Expected: HTTP `200` with the required JSON fields:

```txt
ticket_id
relevant_transaction_id
evidence_verdict
case_type
severity
department
agent_summary
recommended_next_action
customer_reply
human_review_required
confidence
reason_codes
```

---

## 6. Verify Official Public Samples

```bash
python verify_sample_cases.py
```

Expected:

```txt
SUCCESS: All sample cases match expected core fields perfectly.
```

If some samples fail, inspect these core fields first:

```txt
case_type
relevant_transaction_id
evidence_verdict
severity
department
human_review_required
```

---

## 7. Docker Run

Build image:

```bash
docker build -t queuestorm-investigator .
```

Run container:

```bash
docker run -p 8000:8000 --env-file .env.example queuestorm-investigator
```

Test:

```bash
curl http://localhost:8000/health
```

---

## 8. Deployment Notes

For Render, Railway, Fly.io, EC2, Poridhi Lab, or another VM, use:

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Required exposed endpoints:

```txt
GET /health
POST /analyze-ticket
```

The judge should not need login, dashboard access, manual approval, or private network access.

Submit the base URL only, for example:

```txt
https://your-service.example.com
```

Do not submit:

```txt
https://your-service.example.com/health
```

---

## 9. Troubleshooting

### `/health` returns 404

Check that the submitted base URL is correct and does not already include `/health`.

Correct:

```txt
https://your-service.example.com
```

Incorrect:

```txt
https://your-service.example.com/health
```

### Invalid JSON response

Make sure the endpoint returns `application/json` and no extra logs are printed into the response body.

### 400 or 422 on valid input

Check request field names and enum values.

### Timeout

Use local heuristic mode or reduce Gemini timeout:

```env
REQUEST_TIMEOUT_SEC=10.0
```

The service should still return a fallback response if Gemini fails.

### Gemini API issue

Leave `GEMINI_API_KEY` empty or provide a valid key through environment variables.

Never commit the key.

---

## 10. Safety Verification

Before final submission, test complaints containing:

```txt
OTP
PIN
password
refund
reverse
account unblock
fake call
phishing
```

The customer reply must not ask for credentials and must not promise financial actions.

Safe behavior examples:

```txt
Please do not share your PIN or OTP with anyone.
```

```txt
Any eligible amount will be returned through official channels.
```

Unsafe behavior examples:

```txt
Please share your OTP for verification.
```

```txt
We will refund you.
```

```txt
Your account will be unblocked.
```

---

## 11. Final Pre-Submit Checklist

- `/health` returns `{"status":"ok"}`
- `/analyze-ticket` accepts JSON and returns JSON
- Required fields are present
- Enum values exactly match the official problem statement
- Public sample cases are verified
- No real `.env` file is committed
- No real API key or secret is committed
- README is complete
- RUNBOOK is complete
- `sample_request.json` and `sample_response.json` are included
- Live endpoint or Docker fallback is ready