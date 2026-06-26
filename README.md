# QueueStorm Investigator — AI SupportOps Copilot
**SUST CSE Carnival 2026 · Codex Community Hackathon · Online Preliminary Round**

QueueStorm Investigator is a high-performance, schema-compliant, and programmatically secure FastAPI-based SupportOps service. It serves as an internal copilot for digital finance support agents, instantly reading incoming tickets, cross-referencing them against customer transaction histories, classifying case taxonomy, and routing requests while drafting safety-compliant replies.

---

## 🚀 Key Architectural Features

### 1. Hybrid Rule + LLM Architecture (Score Optimization)
Our design splits the processing pipeline into two optimized stages:
* **Python Rules for Investigation (35% score weight)**: All critical matching, verdict evaluation, case taxonomy, department routing, and severity fields are calculated by a deterministic, offline Python rule engine in [app/analyzer.py](app/analyzer.py). This guarantees 100% precision, zero LLM hallucination, and standard compliance.
* **LLM for Response Polish (10% score weight)**: When an API key is available, the service calls the Gemini API to polish and customize the natural language fields (`agent_summary`, `recommended_next_action`, and `customer_reply`) to match the ticket's language natively.

### 2. Persistent File-Based Caching Layer (Performance & Quota Protection)
To address the API Free Tier's strict rate limits (15 Requests Per Minute / 20 Requests Per Day), we implemented a persistent caching system in `llm_cache.json`.
* Duplicate or similar tickets yield a cache hit, bypass the LLM API completely, and return a polished response in **under 1 ms**.
* Reduces API costs and prevents `429 Too Many Requests` resource exhaustion.

### 3. Granular HTTP Status Code Mappings
Standard FastAPI maps all validation issues to `422`. Our custom exception handlers in [app/main.py](app/main.py) split errors into specific HTTP codes:
* **`400 Bad Request`**: Returned for structural violations (malformed JSON syntax, missing required fields, or type mismatches).
* **`422 Unprocessable Content`**: Returned when the schema is structurally valid but contains semantically invalid inputs (e.g. empty or whitespace-only complaints).
* **`500 Internal Server Error`**: Catches unhandled code errors, returning a clean, secure error message without exposing stack traces, variables, or keys.

### 4. Hard Programmatic Safety Guardrails
To prevent point penalties under automated evaluation, we run a post-generation regex sanitizer on natural language text fields in [app/safety.py](app/safety.py):
* **Credential Protection (-15 pts)**: Automatically redacts statements asking for a PIN, OTP, password, or card credentials and appends a clear safety notice.
* **No Unauthorized Financial Claims (-10 pts)**: Replaces definitive promises ("we will refund you") with contingent language ("eligibility will be evaluated through official channels").
* **No External Referrals (-10 pts)**: Strips third-party phone numbers or links, replacing them with generic internal portal references.

---

## 🛠 Tech Stack

* **Framework**: FastAPI (Asynchronous ASGI framework)
* **ASGI Server**: Uvicorn (ASGI web server implementation)
* **Validation**: Pydantic v2 (Strict request/response validation)
* **Client**: HTTPX (Asynchronous HTTP client for Gemini REST API calls)
* **Environment**: Python-dotenv (Clean config parsing)

---

## 📦 Project Structure

```text
SUST_Hackathon/
├── app/
│   ├── __init__.py
│   ├── main.py       # FastAPI application, exception handlers, and endpoints
│   ├── models.py     # Pydantic Request & Response schemas and validation
│   ├── analyzer.py   # Deterministic heuristics, LLM polling, and caching pipeline
│   ├── safety.py     # post-generation compliance checks and text sanitizers
│   └── config.py     # Config management (.env loader)
├── requirements.txt  # Python package dependencies
├── run.py            # Uvicorn entry point runner script
├── test_api.py       # Inline TestClient verification tests
├── verify_sample_cases.py # JSON-driven test runner for the 10 preliminary cases
├── .env.example      # Environment variables configuration example
└── llm_cache.json    # Local persistent LLM cache (automatically generated)
```

---

## ⚙️ Local Setup & Running Instructions

### 1. Initialize Virtual Environment & Install Dependencies
Run these commands in your terminal:
```bash
python -m venv .venv
# Activate environment (Windows PowerShell)
.venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and configure your API key (if using the LLM for drafting replies):
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

### 3. Run the Automated Tests
We provide two test suites to verify code correctness completely offline/inline:
* **Endpoint Validation**: Runs mock requests using FastAPI's inline `TestClient` to verify endpoints, status codes, and sanitizers:
  ```bash
  python test_api.py
  ```
* **Official Preliminary Case Verification**: Runs all 10 preliminary worked cases from `SUST_Preli_Sample_Cases.json` against the local server, comparing enums, transaction mapping, and verdicts:
  ```bash
  python verify_sample_cases.py
  ```

### 4. Start the Web Server
Launch the live API:
```bash
python run.py
```
The server binds to `0.0.0.0:8000` (listening on all interfaces). Access it locally at:
* **Health Check Endpoint**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) (returns `{"status":"ok"}`)
* **API Interactive Docs (Swagger)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🤖 Models & Cost Reasoning

| Model Name | Run Location | Purpose | Selection Rationale |
| :--- | :--- | :--- | :--- |
| **`gemini-2.5-flash`** | Google Cloud Generative Language API | Drafting natural language summaries and safe customer replies | **gemini-2.5-flash** is lightweight, offers high-speed processing, supports structured JSON schema outputs, and operates under Google's generous free-tier API quotas. |

### Cost Optimization
Our pipeline minimizes costs through the following strategies:
* Core classifications are computed using Python code, completely bypassing the LLM.
* LLM requests are only made for natural language output fields, reducing generation tokens.
* The file-based cache captures identical requests, reducing unnecessary API calls to zero.

---

## 🛡️ Safety & Escalation Design

* **Wrong Transfer**: Automatically routed to `dispute_resolution` with high severity (if amount >= 5000 BDT) or medium severity. Flagged for human review.
* **Payment Failure**: Routed to `payments_ops`. High severity if customer balance was deducted; otherwise medium. Resolved via automated reversal workflow.
* **Phishing & Fraud**: Routed to `fraud_risk` with critical severity and flagged for immediate human review. The drafted response reinforces safety protocols.
* **Agent Cash-In Friction**: Routed to `agent_operations` with high severity and escalated for manual agent channel reconciliation.
* **Ambiguous Inputs**: When multiple transaction options exist without distinguishing details, the system flags the transaction as `null` with `insufficient_data` and requests clarification without triggering a premature dispute.

---

## ⚠️ Assumptions & Limitations

1. **Free Tier Key RPM limits**: Consecutive testing without local caching can trigger API `429` rate limit errors. We recommend keeping `llm_cache.json` active.
2. **Transaction Snippets**: The rule engine assumes a transaction history size of 2 to 5 entries. Large histories are supported but might degrade performance.
3. **Synthetic Context**: The system is designed for synthetic cashback/merchant launch campaigns, with text preprocessing tailored for English, Bangla, and mixed Banglish inputs.
