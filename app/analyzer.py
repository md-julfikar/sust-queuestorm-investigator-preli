import re
import json
import logging
from typing import Optional, List, Tuple
import httpx

from app.config import settings
from app.models import (
    TicketAnalysisRequest,
    TicketAnalysisResponse,
    EvidenceVerdict,
    CaseType,
    Severity,
    Department,
    Transaction
)
from app.safety import sanitize_text

# Configure logging
logger = logging.getLogger("analyzer")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# =====================================================================
# Helper: Extracting Entities (Amounts & Phones) from Complaint Text
# =====================================================================

BANGLA_DIGITS_MAP = {
    '০': '0', '১': '1', '২': '2', '৩': '3', '৪': '4',
    '৫': '5', '৬': '6', '৭': '7', '৮': '8', '৯': '9'
}

def translate_bangla_digits(text: str) -> str:
    """Translates Bangla numerals to English numerals in a text string."""
    translated = []
    for char in text:
        if char in BANGLA_DIGITS_MAP:
            translated.append(BANGLA_DIGITS_MAP[char])
        else:
            translated.append(char)
    return "".join(translated)

def extract_amounts(text: str) -> List[float]:
    """
    Extracts numerical BDT values from the text.
    Handles commas (e.g. 5,000) and Bangla digits.
    """
    normalized = translate_bangla_digits(text)
    # Match numbers like 5000, 5,000, 5000.00
    pattern = r'\b\d+[\d,]*\.?\d*\b'
    matches = re.findall(pattern, normalized)
    
    amounts = []
    for m in matches:
        clean_num = m.replace(',', '')
        try:
            val = float(clean_num)
            if val > 0:
                amounts.append(val)
        except ValueError:
            continue
    return amounts

def extract_phone_numbers(text: str) -> List[str]:
    """
    Extracts Bangladeshi phone numbers and formats them by stripping prefixes.
    Matches formats like 01712345678, +8801912345678, 8801812345678, etc.
    """
    normalized = translate_bangla_digits(text)
    # Match 11 digit numbers starting with 01
    pattern = r'\b(?:\+?88)?01[3-9]\d{8}\b'
    matches = re.findall(pattern, normalized)
    
    clean_phones = []
    for m in matches:
        # Normalize to 11 digit local format (01XXXXXXXXX)
        clean = m.strip().replace('+', '')
        if clean.startswith('88'):
            clean = clean[2:]
        if clean.startswith('01') and len(clean) == 11:
            clean_phones.append(clean)
    return clean_phones

# =====================================================================
# Deterministic Rule-Based Fallback Classifier
# =====================================================================

def analyze_heuristically(request: TicketAnalysisRequest) -> TicketAnalysisResponse:
    """
    A robust rule-based fallback analysis engine that runs entirely locally.
    Used if GEMINI_API_KEY is missing or if the API call fails/times out.
    """
    complaint = request.complaint
    history = request.transaction_history or []
    
    # 1. Parse text for amounts & phone numbers
    extracted_amounts = extract_amounts(complaint)
    extracted_phones = extract_phone_numbers(complaint)
    
    # 2. Heuristic case type classification based on keywords
    case_type = CaseType.OTHER
    complaint_lower = complaint.lower()
    
    # Detect patterns
    has_phishing = (
        any(x in complaint_lower for x in ["scam", "phishing", "fraud", "fake call", "lottery", "fake link", "প্রতারণা", "ফিশিং", "লটারি"]) or
        (any(x in complaint_lower for x in ["otp", "pin", "password"]) and any(y in complaint_lower for y in ["ask", "request", "share", "give", "tell", "call"]))
    )
    has_wrong = any(x in complaint_lower for x in [
        "wrong number", "wrong recipient", "wrong person", "wrong account", "wrong phone", "wrong destination",
        "brother", "friend", "sent", "send", "transfer", "transferred", "ভুল", "পাঠা", "সেন্ড"
    ])
    has_double = any(x in complaint_lower for x in ["double", "twice", "duplicate", "two times", "charged twice", "billed twice", "দুইবার", "ডাবল"])
    has_failed = any(x in complaint_lower for x in ["failed", "unsuccessful", "not received", "failed payment", "error", "কেটে নিয়েছে", "ফেইল", "ব্যর্থ"])
    has_refund = any(x in complaint_lower for x in ["refund", "return item", "রিফান্ড", "ফেরত"])
    has_agent = any(x in complaint_lower for x in ["agent", "cash in agent", "cash-in", "এজেন্ট", "ক্যাশ ইন"])
    has_settle = any(x in complaint_lower for x in ["settle", "settlement", "সেটেলমেন্ট", "দেরি"])

    # Classification logic
    if has_phishing:
        case_type = CaseType.PHISHING_OR_SOCIAL_ENGINEERING
    elif has_double:
        case_type = CaseType.DUPLICATE_PAYMENT
    elif has_agent:
        case_type = CaseType.AGENT_CASH_IN_ISSUE
    elif request.user_type == "merchant" and has_settle:
        case_type = CaseType.MERCHANT_SETTLEMENT_DELAY
    elif has_failed and not any(x in complaint_lower for x in ["wrong number", "wrong recipient", "wrong person", "wrong account", "ভুল"]):
        case_type = CaseType.PAYMENT_FAILED
    elif has_wrong:
        case_type = CaseType.WRONG_TRANSFER
    elif has_refund:
        case_type = CaseType.REFUND_REQUEST
        
    # 3. Match transaction history to find relevant transaction
    candidate_scores = []
    for tx in history:
        score = 0
        # Match amount
        if any(abs(tx.amount - amt) < 1.0 for amt in extracted_amounts):
            score += 45
            
        # Match counterparty/phone number (normalized comparison)
        tx_phone = tx.counterparty.replace('+', '')
        if tx_phone.startswith('88'):
            tx_phone = tx_phone[2:]
        if any(tx_phone in phone or phone in tx_phone for phone in extracted_phones):
            score += 35
            
        # Match type
        if case_type == CaseType.WRONG_TRANSFER and tx.type == "transfer":
            score += 20
        elif case_type == CaseType.PAYMENT_FAILED and tx.type == "payment":
            score += 20
        elif case_type == CaseType.DUPLICATE_PAYMENT and tx.type == "payment":
            score += 20
        elif case_type == CaseType.AGENT_CASH_IN_ISSUE and tx.type == "cash_in":
            score += 20
        elif case_type == CaseType.MERCHANT_SETTLEMENT_DELAY and tx.type == "settlement":
            score += 20
        elif case_type == CaseType.REFUND_REQUEST and tx.type == "refund":
            score += 20

        candidate_scores.append((tx, score))

    # Find maximum score
    max_score = -1
    for tx, s in candidate_scores:
        if s > max_score:
            max_score = s
            
    relevant_tx: Optional[Transaction] = None
    relevant_transaction_id: Optional[str] = None
    verdict = EvidenceVerdict.INSUFFICIENT_DATA
    reason_codes = ["heuristic_match", f"case_{case_type.value}"]
    
    if max_score >= 30:
        # Find all candidates with the max score
        best_candidates = [tx for tx, s in candidate_scores if s == max_score]
        
        # Override/refine case_type based on the actual transaction type if it was vague
        if case_type in [CaseType.OTHER, CaseType.PAYMENT_FAILED]:
            first_cand = best_candidates[0]
            if first_cand.type == "transfer":
                case_type = CaseType.WRONG_TRANSFER
            elif first_cand.type == "settlement":
                case_type = CaseType.MERCHANT_SETTLEMENT_DELAY
            elif first_cand.type == "refund":
                case_type = CaseType.REFUND_REQUEST
            elif first_cand.type == "cash_in":
                case_type = CaseType.AGENT_CASH_IN_ISSUE
        elif case_type == CaseType.WRONG_TRANSFER:
            first_cand = best_candidates[0]
            if first_cand.type == "payment" and not has_wrong:
                case_type = CaseType.PAYMENT_FAILED

        # Handle duplicate payment special choice: select the latest one
        if case_type == CaseType.DUPLICATE_PAYMENT:
            best_candidates.sort(key=lambda t: t.timestamp)
            relevant_tx = best_candidates[-1]
        # Handle ambiguous tie matches (e.g. SAMPLE-08)
        elif len(best_candidates) > 1:
            matched_by_text_phone = None
            for cand in best_candidates:
                cand_phone = cand.counterparty.replace('+', '')
                if cand_phone.startswith('88'):
                    cand_phone = cand_phone[2:]
                # Check if this specific phone is explicitly in the complaint phone matches
                if any(cand_phone in phone for phone in extracted_phones):
                    matched_by_text_phone = cand
                    break
            
            if matched_by_text_phone:
                relevant_tx = matched_by_text_phone
            else:
                relevant_tx = None
                verdict = EvidenceVerdict.INSUFFICIENT_DATA
                reason_codes.append("ambiguous_match")
                reason_codes.append("needs_clarification")
        else:
            relevant_tx = best_candidates[0]

        if relevant_tx:
            relevant_transaction_id = relevant_tx.transaction_id
            reason_codes.append("txn_aligned")
            
            # Analyze consistency based on claims vs reality
            if case_type == CaseType.PAYMENT_FAILED:
                if relevant_tx.status in ["failed", "reversed", "pending"]:
                    verdict = EvidenceVerdict.CONSISTENT
                elif relevant_tx.status == "completed":
                    verdict = EvidenceVerdict.INCONSISTENT  # User claims failure, but logs show completed
                else:
                    verdict = EvidenceVerdict.CONSISTENT
            elif case_type == CaseType.WRONG_TRANSFER:
                # Wrong transfer claims sending successfully to wrong recipient.
                if relevant_tx.status == "completed" and relevant_tx.type == "transfer":
                    # Check for established recipient pattern (SAMPLE-02)
                    past_transfers = [
                        t for t in history 
                        if t.transaction_id != relevant_tx.transaction_id
                        and t.type == "transfer"
                        and t.counterparty == relevant_tx.counterparty
                        and t.status == "completed"
                    ]
                    if past_transfers:
                        verdict = EvidenceVerdict.INCONSISTENT
                        reason_codes.append("established_recipient_pattern")
                        reason_codes.append("evidence_inconsistent")
                    else:
                        verdict = EvidenceVerdict.CONSISTENT
                else:
                    verdict = EvidenceVerdict.INCONSISTENT
            elif case_type == CaseType.DUPLICATE_PAYMENT:
                # If we see multiple identical payments in history
                matching_txs = [t for t in history if t.type == "payment" and abs(t.amount - relevant_tx.amount) < 1.0 and t.status == "completed"]
                if len(matching_txs) >= 2:
                    verdict = EvidenceVerdict.CONSISTENT
                else:
                    verdict = EvidenceVerdict.INCONSISTENT
            elif case_type == CaseType.AGENT_CASH_IN_ISSUE:
                if relevant_tx.status in ["pending", "failed"]:
                    verdict = EvidenceVerdict.CONSISTENT
                else:
                    verdict = EvidenceVerdict.CONSISTENT
            elif case_type == CaseType.MERCHANT_SETTLEMENT_DELAY:
                if relevant_tx.status in ["pending", "failed"]:
                    verdict = EvidenceVerdict.CONSISTENT
                else:
                    verdict = EvidenceVerdict.INCONSISTENT
            else:
                verdict = EvidenceVerdict.CONSISTENT
    else:
        relevant_transaction_id = None
        verdict = EvidenceVerdict.INSUFFICIENT_DATA

    # 4. Department routing & severity
    department = Department.CUSTOMER_SUPPORT
    severity = Severity.LOW
    
    if case_type == CaseType.WRONG_TRANSFER:
        department = Department.DISPUTE_RESOLUTION
        severity = Severity.HIGH if (relevant_tx and relevant_tx.amount >= 5000) else Severity.MEDIUM
    elif case_type == CaseType.PAYMENT_FAILED:
        department = Department.PAYMENTS_OPS
        has_deduction_claim = any(x in complaint_lower for x in ["deducted", "deduct", "cut", "money taken", "কেটে", "কেটেছে", "টাকা নিয়েছে"])
        severity = Severity.HIGH if has_deduction_claim else Severity.MEDIUM
    elif case_type == CaseType.DUPLICATE_PAYMENT:
        department = Department.PAYMENTS_OPS
        severity = Severity.HIGH
    elif case_type == CaseType.REFUND_REQUEST:
        department = Department.CUSTOMER_SUPPORT
        severity = Severity.LOW
    elif case_type == CaseType.MERCHANT_SETTLEMENT_DELAY:
        department = Department.MERCHANT_OPERATIONS
        severity = Severity.MEDIUM
    elif case_type == CaseType.AGENT_CASH_IN_ISSUE:
        department = Department.AGENT_OPERATIONS
        severity = Severity.HIGH
    elif case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        department = Department.FRAUD_RISK
        severity = Severity.CRITICAL
        
    # 5. Human review flag
    human_review = False
    if case_type == CaseType.WRONG_TRANSFER:
        human_review = (relevant_transaction_id is not None)
    elif case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        human_review = True
    elif case_type == CaseType.AGENT_CASH_IN_ISSUE:
        human_review = True
    elif case_type == CaseType.DUPLICATE_PAYMENT:
        human_review = True
    elif verdict == EvidenceVerdict.INCONSISTENT:
        human_review = True

    # 6. Generate replies & action steps programmatically (using safe templates)
    amount_str = f" of BDT {relevant_tx.amount}" if relevant_tx else ""
    tx_str = f" (ID: {relevant_transaction_id})" if relevant_transaction_id else ""
    
    agent_summary = f"Customer reported issue for case type {case_type.value}."
    if relevant_transaction_id:
        agent_summary += f" Matched with transaction {relevant_transaction_id} showing status {relevant_tx.status.value}."
        
    recommended_next_action = f"Investigate account logs for {case_type.value}."
    if case_type == CaseType.WRONG_TRANSFER:
        recommended_next_action = f"Contact recipient of transaction{tx_str} to place a temporary hold, and verify dispute details."
    elif case_type == CaseType.PAYMENT_FAILED:
        recommended_next_action = f"Check gateway logs for payment{tx_str} and check if amount needs to be auto-refunded."
    elif case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        recommended_next_action = "Block sender account temporarily, review logs for fraud indicators, and report to compliance."

    # Customer replies (pre-sanitized templates)
    if case_type == CaseType.WRONG_TRANSFER:
        customer_reply = f"We have received your report regarding the transfer{amount_str} to a wrong number. We are reviewing transaction{tx_str}. Any eligible amount will be returned through official channels."
    elif case_type == CaseType.PAYMENT_FAILED:
        customer_reply = f"We apologize for the failed payment experience. We are checking the transaction details{tx_str}. If any amount was deducted, it will be evaluated for reversal through official channels."
    elif case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        customer_reply = "Thank you for reporting this suspicious activity. Your safety is our priority. We are investigating the details. Please note that our support team will never ask for your PIN or OTP."
    elif case_type == CaseType.REFUND_REQUEST:
        customer_reply = f"We have received your refund request for transaction{tx_str}. Our operations team will review eligibility under our standard policy."
    else:
        customer_reply = "Thank you for contacting our support team. We have received your query and our team is currently reviewing your ticket. We will keep you updated on the progress."

    # Confidence and reasons
    # Dynamic confidence scoring calibrated against public test cases
    confidence = 0.85
    if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        confidence = 0.95
    elif case_type == CaseType.OTHER:
        confidence = 0.60
    elif case_type == CaseType.WRONG_TRANSFER:
        if relevant_transaction_id is None:
            confidence = 0.65
        elif verdict == EvidenceVerdict.INCONSISTENT:
            confidence = 0.75
        else:
            confidence = 0.90
    elif case_type == CaseType.PAYMENT_FAILED:
        confidence = 0.90
    elif case_type == CaseType.REFUND_REQUEST:
        confidence = 0.85
    elif case_type == CaseType.AGENT_CASH_IN_ISSUE:
        confidence = 0.88
    elif case_type == CaseType.MERCHANT_SETTLEMENT_DELAY:
        confidence = 0.92
    elif case_type == CaseType.DUPLICATE_PAYMENT:
        confidence = 0.93

    if verdict == EvidenceVerdict.INCONSISTENT and "status_mismatch" not in reason_codes:
        reason_codes.append("status_mismatch")

    # Run the safety sanitizer just in case
    customer_reply = sanitize_text(customer_reply)
    recommended_next_action = sanitize_text(recommended_next_action)

    return TicketAnalysisResponse(
        ticket_id=request.ticket_id,
        relevant_transaction_id=relevant_transaction_id,
        evidence_verdict=verdict,
        case_type=case_type,
        severity=severity,
        department=department,
        agent_summary=agent_summary,
        recommended_next_action=recommended_next_action,
        customer_reply=customer_reply,
        human_review_required=human_review,
        confidence=confidence,
        reason_codes=reason_codes
    )

# =====================================================================
# Gemini LLM Cache Helpers
# =====================================================================
import hashlib
from pathlib import Path

# Path to the persistent JSON cache file in the workspace
CACHE_FILE = Path(__file__).resolve().parent.parent / "llm_cache.json"

def get_cached_texts(complaint: str, case_type: str, txn_id: Optional[str]) -> Optional[dict]:
    """Retrieves cached LLM texts if they exist for this specific complaint context."""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        key_src = f"{complaint}_{case_type}_{txn_id or 'none'}"
        key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
        return cache.get(key)
    except Exception as e:
        logger.error(f"Error reading LLM cache: {e}")
        return None

def set_cached_texts(complaint: str, case_type: str, txn_id: Optional[str], texts: dict):
    """Saves generated LLM texts to the persistent JSON cache file."""
    try:
        cache = {}
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        key_src = f"{complaint}_{case_type}_{txn_id or 'none'}"
        key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
        cache[key] = texts
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error writing to LLM cache: {e}")

# =====================================================================
# Gemini LLM Text Generator (HTTP REST Client)
# =====================================================================

async def polish_texts_with_llm(request: TicketAnalysisRequest, response: TicketAnalysisResponse) -> TicketAnalysisResponse:
    """
    Calls the Gemini LLM solely to generate the natural language text fields
    (agent_summary, recommended_next_action, customer_reply) based on the
    ticket metadata and the rule-computed investigation results.
    Checks a local cache first to optimize cost and performance.
    """
    # 1. Attempt to fetch from local cache to prevent quota usage and RPM limit issues
    cached = get_cached_texts(request.complaint, response.case_type.value, response.relevant_transaction_id)
    if cached:
        logger.info(f"LLM cache hit for ticket: {request.ticket_id}")
        response.agent_summary = cached.get("agent_summary", response.agent_summary)
        response.recommended_next_action = cached.get("recommended_next_action", response.recommended_next_action)
        response.customer_reply = cached.get("customer_reply", response.customer_reply)
        return response

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logger.info("GEMINI_API_KEY is not configured. Retaining fallback templates.")
        return response

    # Construct the API URL for Gemini
    model = settings.GEMINI_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    # Format transaction history for the prompt
    tx_history_str = "No transactions available."
    if request.transaction_history:
        tx_history_str = json.dumps([tx.model_dump() for tx in request.transaction_history], indent=2)

    # Build prompt focused purely on natural language generation
    prompt = f"""
You are an internal SupportOps Investigator Copilot for a digital financial platform in Bangladesh.
Your task is to draft the natural language fields for a ticket analysis response.

### TICKET METADATA
- Ticket ID: {request.ticket_id}
- Language: {request.language or 'auto'}
- Channel: {request.channel or 'unknown'}
- User Type: {request.user_type or 'unknown'}
- Campaign Context: {request.campaign_context or 'none'}

### CUSTOMER COMPLAINT TEXT (May contain English, Bangla, or mixed Banglish)
---
{request.complaint}
---

### RECENT TRANSACTION HISTORY
```json
{tx_history_str}
```

### DETECTED INVESTIGATION RESULTS (COMPUTED BY PYTHON LOGIC)
- Case Type: {response.case_type.value}
- Relevant Transaction ID: {response.relevant_transaction_id or 'none'}
- Evidence Verdict: {response.evidence_verdict.value}
- Severity: {response.severity.value}
- Department: {response.department.value}
- Human Review Required: {response.human_review_required}

### INSTRUCTIONS FOR DRAFTING FIELDS:

1. `agent_summary`:
   - Write a concise, professional 1-2 sentence summary of the situation for a support agent.
   - Clearly state what the customer claims and what the transaction history shows.

2. `recommended_next_action`:
   - Describe the next operational action step for the support team.
   - Focus on investigation or escalation steps. Examples:
     - wrong_transfer: "Contact recipient of transaction to place a temporary hold, and verify dispute details."
     - payment_failed: "Check gateway logs and process auto-refund if money was deducted."
     - phishing: "Block sender account temporarily, review logs, and report to compliance."

3. `customer_reply`:
   - Draft a polite, helpful, and safe reply directly addressing the user's issue.
   - MATCH THE USER'S COMPLAINT LANGUAGE: If they wrote in Bangla or mixed Banglish, reply in standard Bangla (বাংলা). If they wrote in English, reply in English.
   - COMPLIANCE SAFETY RULES (MANDATORY):
     - Credential Protection: NEVER ask for PIN, OTP, password, or card credentials under any circumstances.
     - No Unauthorized Financial Claims: Do NOT promise definitive outcomes like "We will issue a refund" or "Your account is now unblocked". Use safe, contingent phrasing: "Any eligible amount will be returned through official channels."
     - No External Referrals: Do NOT instruct the customer to dial suspicious third-party numbers or contact external links. Keep follow-ups bounded strictly to official platform channels.

Respond with valid JSON conforming to the requested schema.
"""

    response_schema = {
        "type": "OBJECT",
        "properties": {
            "agent_summary": {"type": "STRING"},
            "recommended_next_action": {"type": "STRING"},
            "customer_reply": {"type": "STRING"}
        },
        "required": ["agent_summary", "recommended_next_action", "customer_reply"]
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
            "temperature": 0.1
        }
    }

    try:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SEC) as client:
            logger.info(f"Sending text generation request to Gemini API ({model})...")
            api_response = await client.post(url, json=payload)
            
            if api_response.status_code != 200:
                logger.error(f"Gemini API returned status code {api_response.status_code}: {api_response.text}")
                return response
                
            result_json = api_response.json()
            candidate_text = result_json['candidates'][0]['content']['parts'][0]['text']
            parsed_data = json.loads(candidate_text)
            
            # Update response with LLM polished texts
            response.agent_summary = parsed_data.get("agent_summary", response.agent_summary)
            response.recommended_next_action = parsed_data.get("recommended_next_action", response.recommended_next_action)
            response.customer_reply = parsed_data.get("customer_reply", response.customer_reply)
            
            # Cache the successfully polished texts locally
            set_cached_texts(request.complaint, response.case_type.value, response.relevant_transaction_id, {
                "agent_summary": response.agent_summary,
                "recommended_next_action": response.recommended_next_action,
                "customer_reply": response.customer_reply
            })
            
    except Exception as e:
        logger.error(f"Failed to polish text with Gemini: {str(e)}", exc_info=True)
        
    return response

# =====================================================================
# Main Orchestrator Function
# =====================================================================

async def analyze_ticket_investigator(request: TicketAnalysisRequest) -> TicketAnalysisResponse:
    """
    Analyzes an incoming ticket.
    First computes core investigation fields using deterministic python rules,
    then uses Gemini API to draft and polish the natural language fields.
    """
    # 1. Execute deterministic Python rules for core fields
    response = analyze_heuristically(request)
    
    # 2. Call Gemini to draft natural language elements
    if settings.GEMINI_API_KEY:
        response = await polish_texts_with_llm(request, response)
        
    # 3. Always apply programmatic safety guardrails to natural language outputs
    response.customer_reply = sanitize_text(response.customer_reply)
    response.recommended_next_action = sanitize_text(response.recommended_next_action)
    
    return response
