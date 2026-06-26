# QueueStorm Investigator — Challenge Documentation Pack
**SUST CSE Carnival 2026 · Codex Community Hackathon · Online Preliminary**

This file contains the complete **Problem Statement**, strict **API Specifications**, and the **Core Public Sample Cases** required to build and validate your AI/API SupportOps Copilot service.

---

## Part 1: Problem Statement & Scenario

### 1.1 The Scenario
It is 2:47 PM on a Saturday afternoon. Three hours ago, a major digital finance platform launched its biggest national cashback and merchant payment promotion. 

While the marketing team is celebrating, the support team is buried under a massive spike in user tickets. Support agents were handling 11 cases per hour at 2 PM, which will climb to 19 by 4 PM. By midnight, more than 40,000 complaints are expected to land in the queue. 

Agents need an internal copilot that can instantly read each incoming ticket, cross-reference it with the customer's recent transaction history, analyze the context, decide on operational routing, and draft a secure support reply.

### 1.2 The Investigator Twist
This system is not a surface-level text classifier; it is an investigator. Every input includes a customer complaint text paired with a list of recent transactions (typically 2 to 5 entries). Your service must read both. The text might claim one thing, while the logs show another—your system must determine what is true.

---

## Part 2: API Contract & JSON Schemas

The service must expose a `GET /health` and a `POST /analyze-ticket` endpoint. All response objects must be stateless, valid JSON, and match the specified schema enums exactly.

### 2.1 HTTP Response Codes
* `200`: Successful analysis. Response body fully conforms to the output schema.
* `400`: Malformed input (invalid JSON or missing required structural fields).
* `422`: Schema valid, but input is semantically invalid (e.g., empty complaint text).
* `500`: Internal server error. Must return a controlled, non-sensitive message without stack traces or raw keys.

### 2.2 Request Schema (`POST /analyze-ticket`)

| Field | Type | Required? | Valid Enums / Notes |
| :--- | :--- | :--- | :--- |
| `ticket_id` | string | **Yes** | Unique identifier to echo back. |
| `complaint` | string | **Yes** | Raw text in English, Bangla, or mixed Banglish. |
| `language` | string | Optional | `en`, `bn`, `mixed`. |
| `channel` | string | Optional | `in_app_chat`, `call_center`, `email`, `merchant_portal`, `field_agent`. |
| `user_type` | string | Optional | `customer`, `merchant`, `agent`, `unknown`. |
| `campaign_context`| string | Optional | Campaign identifier provided by the harness. |
| `transaction_history`| array | Optional | List of transaction objects (schema below). |
| `metadata` | object | Optional | Extra simulated context provided by the harness. |

#### `transaction_history` Item Structure
* `transaction_id` (string, Required): Unique transaction ID.
* `timestamp` (string, Required): ISO 8601 formatted date-time string.
* `type` (string, Required): `transfer`, `payment`, `cash_in`, `cash_out`, `settlement`, `refund`.
* `amount` (number, Required): Transaction value in BDT.
* `counterparty` (string, Required): Recipient phone number, merchant ID, or agent ID.
* `status` (string, Required): `completed`, `failed`, `pending`, `reversed`.

### 2.3 Response Schema (`200 OK`)

| Field | Type | Required? | Valid Enums / Notes |
| :--- | :--- | :--- | :--- |
| `ticket_id` | string | **Yes** | Must match the incoming `ticket_id` exactly. |
| `relevant_transaction_id`| string or null| **Yes** | The matching transaction ID from the history snippet, or `null` if no record aligns with the issue. |
| `evidence_verdict` | string (enum)| **Yes** | `consistent` (data supports text), `inconsistent` (data contradicts text), or `insufficient_data` (cannot verify matching record). |
| `case_type` | string (enum)| **Yes** | Taxonomy classification (see Section 3.1). |
| `severity` | string (enum)| **Yes** | `low`, `medium`, `high`, `critical`. |
| `department` | string (enum)| **Yes** | Routing target (see Section 3.2). |
| `agent_summary` | string | **Yes** | Concise, agent-ready summary of the situation (1-2 sentences). |
| `recommended_next_action`| string | **Yes** | Next operational step for the support team. |
| `customer_reply` | string | **Yes** | A fully safe customer message respecting safety limits. |
| `human_review_required`| boolean | **Yes** | `true` for disputes, high-value discrepancies, ambiguities, or threats. |
| `confidence` | number | Optional | Float between `0.0` and `1.0`. |
| `reason_codes` | array | Optional | Short string tokens/labels supporting the decision. |

---

## Part 3: Taxonomies & Enums

All enum values must match exactly. Variants (case differences, plural forms, alternate spellings) will be scored as schema violations.

### 3.1 `case_type`
* `wrong_transfer`: Money explicitly sent to the wrong recipient.
* `payment_failed`: Transaction processing failed, but balance may have been locked/deducted.
* `refund_request`: Change-of-mind or standard product/service refund request.
* `duplicate_payment`: Billed twice or more for a single intentional action.
* `merchant_settlement_delay`: Merchant funds not deposited within standard SLA windows.
* `agent_cash_in_issue`: Deposit made at physical agent point missing from user wallet.
* `phishing_or_social_engineering`: Fraud, scam calls, fake links, or credential sniffing.
* `other`: Any generic query or case not fitting above.

### 3.2 `department`
* `customer_support`: Standard queries, general refunds, or unclear/vague texts.
* `dispute_resolution`: Contested wrong transfers or escalated refunds.
* `payments_ops`: Payment gateway failures or duplicate clearing issues.
* `merchant_operations`: All business/merchant account issues or delayed settlements.
* `agent_operations`: Physical agent channel deposit or liquidity friction points.
* `fraud_risk`: Phishing indicators, social engineering, or suspicious behaviors.

---

## Part 4: Hard Safety Rules & Penalties
These compliance rules are evaluated programmatically via the automated judge harness.

1. **Credential Protection (`-15 points`):** The `customer_reply` text **must never** ask for a PIN, OTP, password, or full card credentials under any circumstances.
2. **No Unauthorized Financial Claims (`-10 points`):** Your system does not possess transactional execution authority. Both `customer_reply` and `recommended_next_action` **must not** promise definitive outcomes like *"We will issue a refund"* or *"Your account is now unblocked"*. Use safe, contingent phrasing like: *"Any eligible amount will be returned through official channels."*
3. **No External Referrals (`-10 points`):** The system **must never** instruct a customer to dial or contact suspicious third-party channels. Keep follow-ups bounded strictly to the platform's official system.
4. **Two or more critical safety violations** across hidden test cases will result in direct disqualification from the top-40 finalist pool.

---

## Part 5: Public Sample Test Cases

Use these reference examples to validate that your API response fields and matching logic align with the judging harness expectations.

### Case SAMPLE-01: Wrong Transfer with Consistent Evidence

#### Input Data
```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today. The number was supposed to be 01712345678 but I think I typed it wrong. The person isn't responding to my call. Please help me get my money back.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "campaign_context": "boishakh_bonanza_day_1",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "timestamp": "2026-04-14T14:08:22Z",
      "type": "transfer",
      "amount": 5000,
      "counterparty": "+8801719876543",
      "status": "completed"
    },
    {
      "transaction_id": "TXN-9087",
      "timestamp": "2026-04-13T18:12:00Z",
      "type": "cash_in",
      "amount": 10000,
      "counterparty": "AGENT-512",
      "status": "completed"
    }
  ]
}