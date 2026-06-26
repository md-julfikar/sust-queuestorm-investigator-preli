from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator

# =====================================================================
# Request Enums & Sub-models
# =====================================================================

class TransactionType(str, Enum):
    TRANSFER = "transfer"
    PAYMENT = "payment"
    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"
    SETTLEMENT = "settlement"
    REFUND = "refund"

class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    REVERSED = "reversed"

class Transaction(BaseModel):
    transaction_id: str = Field(..., description="Unique transaction ID.")
    timestamp: str = Field(..., description="ISO 8601 formatted date-time string.")
    type: TransactionType = Field(..., description="Type of the transaction.")
    amount: float = Field(..., description="Transaction value in BDT.")
    counterparty: str = Field(..., description="Recipient phone number, merchant ID, or agent ID.")
    status: TransactionStatus = Field(..., description="Current status of the transaction.")

    @field_validator('transaction_id', 'timestamp', 'counterparty')
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} cannot be empty or whitespace only")
        return v

    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v < 0:
            raise ValueError("amount cannot be negative")
        return v

# =====================================================================
# Response Enums
# =====================================================================

class EvidenceVerdict(str, Enum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    INSUFFICIENT_DATA = "insufficient_data"

class CaseType(str, Enum):
    WRONG_TRANSFER = "wrong_transfer"
    PAYMENT_FAILED = "payment_failed"
    REFUND_REQUEST = "refund_request"
    DUPLICATE_PAYMENT = "duplicate_payment"
    MERCHANT_SETTLEMENT_DELAY = "merchant_settlement_delay"
    AGENT_CASH_IN_ISSUE = "agent_cash_in_issue"
    PHISHING_OR_SOCIAL_ENGINEERING = "phishing_or_social_engineering"
    OTHER = "other"

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Department(str, Enum):
    CUSTOMER_SUPPORT = "customer_support"
    DISPUTE_RESOLUTION = "dispute_resolution"
    PAYMENTS_OPS = "payments_ops"
    MERCHANT_OPERATIONS = "merchant_operations"
    AGENT_OPERATIONS = "agent_operations"
    FRAUD_RISK = "fraud_risk"

# =====================================================================
# Primary Request Schema
# =====================================================================

class TicketAnalysisRequest(BaseModel):
    ticket_id: str = Field(..., description="Unique identifier to echo back.")
    complaint: str = Field(..., description="Raw complaint text in English, Bangla, or mixed Banglish.")
    language: Optional[str] = Field(None, description="Language of the complaint: 'en', 'bn', 'mixed'.")
    channel: Optional[str] = Field(None, description="Channel of entry.")
    user_type: Optional[str] = Field(None, description="User type: 'customer', 'merchant', 'agent', 'unknown'.")
    campaign_context: Optional[str] = Field(None, description="Campaign identifier.")
    transaction_history: Optional[List[Transaction]] = Field(default_factory=list, description="List of transaction objects.")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Simulated extra context.")

    @field_validator('complaint')
    @classmethod
    def validate_complaint(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("complaint text cannot be empty or whitespace only")
        return v

    @field_validator('ticket_id')
    @classmethod
    def validate_ticket_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ticket_id cannot be empty or whitespace only")
        return v

# =====================================================================
# Primary Response Schema
# =====================================================================

class TicketAnalysisResponse(BaseModel):
    ticket_id: str = Field(..., description="Must match the incoming ticket_id exactly.")
    relevant_transaction_id: Optional[str] = Field(
        ..., 
        description="Matching transaction ID from the history, or null if no record aligns with the issue."
    )
    evidence_verdict: EvidenceVerdict = Field(..., description="Verification verdict.")
    case_type: CaseType = Field(..., description="Taxonomy classification.")
    severity: Severity = Field(..., description="Case severity level.")
    department: Department = Field(..., description="Routing target department.")
    agent_summary: str = Field(..., description="Concise, agent-ready summary of the situation (1-2 sentences).")
    recommended_next_action: str = Field(..., description="Next operational step for the support team.")
    customer_reply: str = Field(..., description="A fully safe customer message respecting safety limits.")
    human_review_required: bool = Field(..., description="True for disputes, high-value discrepancies, ambiguities, or threats.")
    confidence: Optional[float] = Field(None, description="Float between 0.0 and 1.0.")
    reason_codes: Optional[List[str]] = Field(default_factory=list, description="Short string tokens/labels supporting the decision.")
