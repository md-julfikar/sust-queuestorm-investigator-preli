import re

# =====================================================================
# Safety Rule Constants & Regexes
# =====================================================================

# 1. Credential Protection
# List of words representing PIN, OTP, passwords, etc.
CREDENTIAL_KEYWORDS = [
    r"\bpin\b", r"\botp\b", r"\bpassword\b", r"\bpasscode\b", 
    r"\bcvv\b", r"\bcard credentials\b", r"\bcredentials\b",
    r"\bsecurity code\b", r"\bverification code\b",
    r"পিন", r"ওটিপি", r"পাসওয়ার্ড"  # Bangla translations
]

# 2. No Unauthorized Financial Claims
# Matches definitive refund or unblocking promises.
FINANCIAL_PROMISE_PATTERNS = [
    (re.compile(r"\b(we will|i will|system will|we\'ll) (issue a refund|refund you|refund your|refund the)\b", re.IGNORECASE), 
     "we will evaluate your eligibility for a refund"),
    (re.compile(r"\b(we will|i will|we\'ll) (return your money|send back your money|reverse the transaction|credit your account)\b", re.IGNORECASE),
     "any eligible amount will be processed through official channels"),
    (re.compile(r"\b(your account is|has been|we have)(?:\s+\w+){0,2}\s+(unblocked|activated|restored)\b", re.IGNORECASE),
     "your account status is currently being reviewed for potential resolution"),
    (re.compile(r"\b(refund is|refund has been) (processed|issued|sent|done)\b", re.IGNORECASE),
     "we will evaluate your transaction for eligible resolution"),
    # Bangla versions of definite claims
    (re.compile(r"টাকা ফেরত দেওয়া হবে", re.IGNORECASE), "নিয়ম অনুযায়ী প্রয়োজনীয় ব্যবস্থা নেওয়া হবে"),
    (re.compile(r"রিফান্ড পেয়ে যাবেন", re.IGNORECASE), "যোগ্যতা যাচাই করে পরবর্তী ব্যবস্থা নেওয়া হবে"),
    (re.compile(r"অ্যাকাউন্ট আনব্লক করা হয়েছে", re.IGNORECASE), "অ্যাকাউন্টটি পর্যালোচনার অধীনে রয়েছে")
]

def sanitize_credentials(text: str) -> str:
    """
    Ensures that the text never asks for PIN, OTP, or credentials.
    If it does, we remove the request and append a security disclaimer.
    """
    lower_text = text.lower()
    violation_found = False
    
    for pattern in CREDENTIAL_KEYWORDS:
        if re.search(pattern, lower_text):
            violation_found = True
            break
            
    if violation_found:
        # Strip common sentence structures asking for these
        # E.g., "Please share your OTP.", "Send me your PIN."
        text = re.sub(
            r"(?i)(please\s+)?(share|send|provide|give|tell|enter|type)\s+(us\s+)?(your\s+)?(otp|pin|password|passcode|cvv|credentials|security\s+code)[^.!?]*[.!?]?", 
            "", 
            text
        )
        # Bangla sentence strips
        text = re.sub(
            r"(অনুগ্রহ করে\s+)?(আপনার\s+)?(ওটিপি|পিন|পাসওয়ার্ড)\s+(দিন|শেয়ার করুন|পাঠান)[^.!?]*[.!?]?", 
            "", 
            text
        )
        
        # Append safe disclaimer
        disclaimer = " Please note that our support team will never ask for your PIN, OTP, or password. Keep your credentials secure."
        text = text.strip()
        if not text.endswith(".") and not text.endswith("!") and not text.endswith("?"):
            text += "."
        text += disclaimer
        
    return text.strip()

def sanitize_financial_claims(text: str) -> str:
    """
    Substitutes definitive promises (e.g. "we will refund") with safe, contingent phrasing.
    """
    for pattern, replacement in FINANCIAL_PROMISE_PATTERNS:
        text = pattern.sub(replacement, text)
        
    # Extra check for definitive refund words
    # Replace "Refund will be processed" with "Refund status will be evaluated"
    text = re.sub(r"\b(Refund|reversal) will be (processed|sent|issued)\b", r"\1 status will be evaluated", text, flags=re.IGNORECASE)
    text = re.sub(r"\bWe will refund the money\b", "Any eligible amount will be returned through official channels", text, flags=re.IGNORECASE)
    
    return text

def sanitize_external_referrals(text: str) -> str:
    """
    Identifies and removes third-party contact requests (phone numbers, external URLs, social links).
    Keeps only bounded official references.
    """
    # Remove phone numbers except standard official shortcodes (e.g. 16247 or 3-4 digit numbers)
    # Match standard mobile numbers: +8801..., 01... (11 digits or more)
    text = re.sub(r"\b(\+?88)?01[3-9]\d{8}\b", "our official helpdesk", text)
    
    # Remove external links (http/https/www)
    # E.g., "visit http://scam.com" -> "visit our official portal"
    text = re.sub(r"https?://\S+", "our official website/app", text)
    text = re.sub(r"www\.\S+", "our official website/app", text)
    
    # Remove mentions of third-party channels
    text = re.sub(r"\b(WhatsApp|Telegram|imo|Facebook Messenger)\b", "official in-app chat", text, flags=re.IGNORECASE)
    
    return text

def sanitize_text(text: str) -> str:
    """
    Runs all safety filters sequentially on the text to guarantee compliance.
    """
    if not text:
        return text
    
    text = sanitize_credentials(text)
    text = sanitize_financial_claims(text)
    text = sanitize_external_referrals(text)
    
    return text
