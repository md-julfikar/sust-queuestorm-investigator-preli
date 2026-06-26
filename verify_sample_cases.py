import json
import sys
import time
from fastapi.testclient import TestClient

# Add current workspace to path to import app correctly
from app.main import app

client = TestClient(app)

def run_tests():
    # Load sample cases
    try:
        with open("SUST_Preli_Sample_Cases.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading SUST_Preli_Sample_Cases.json: {e}")
        sys.exit(1)

    cases = data.get("cases", [])
    print(f"Loaded {len(cases)} sample cases.\n")

    passed_count = 0
    total_count = len(cases)

    print(f"{'Case ID':<10} | {'Case Label':<40} | {'Field':<25} | {'Expected':<20} | {'Actual':<20} | {'Status':<6}")
    print("-" * 135)

    for case in cases:
        case_id = case.get("id")
        label = case.get("label")
        case_input = case.get("input")
        expected = case.get("expected_output", {})

        # Call endpoint
        try:
            # Introduce a delay to respect Gemini Free Tier 15 RPM rate limits
            time.sleep(4.0)
            response = client.post("/analyze-ticket", json=case_input)
            actual = response.json()
        except Exception as e:
            print(f"Failed to call API for {case_id}: {e}")
            continue

        if response.status_code != 200:
            print(f"API returned status {response.status_code} for {case_id}: {actual}")
            continue

        # Fields to compare
        compare_fields = [
            "relevant_transaction_id",
            "evidence_verdict",
            "case_type",
            "severity",
            "department",
            "human_review_required"
        ]

        case_passed = True
        discrepancies = []

        for field in compare_fields:
            exp_val = expected.get(field)
            act_val = actual.get(field)

            # Standardize comparisons (e.g. enums)
            if str(exp_val) != str(act_val):
                case_passed = False
                discrepancies.append((field, exp_val, act_val))

        if case_passed:
            passed_count += 1
            print(f"{case_id:<10} | {label:<40} | {'(All Core Fields Match)':<25} | {'-':<20} | {'-':<20} | PASS")
        else:
            print(f"{case_id:<10} | {label:<40} | {'FAILED CORE FIELDS':<25} | {'-':<20} | {'-':<20} | FAIL")
            for field, exp_val, act_val in discrepancies:
                print(f"{'':<10} | {'':<40} | {field:<25} | {str(exp_val):<20} | {str(act_val):<20} | FAIL")
        
        # Output safety compliance status
        reply = actual.get("customer_reply", "")
        action = actual.get("recommended_next_action", "")
        
        # Programmatic check for safety violations in reply
        safety_issues = []
        for kw in ["otp", "pin", "password", "cvv"]:
            if kw in reply.lower() and "never ask" not in reply.lower():
                safety_issues.append(f"Contains credential keyword '{kw}'")
                
        for promise in ["will refund", "will return", "unblocked", "refunded"]:
            if promise in reply.lower() and "eligibility" not in reply.lower() and "evaluated" not in reply.lower() and "reviewed" not in reply.lower() and "channels" not in reply.lower():
                safety_issues.append(f"Definitive promise '{promise}'")

        if safety_issues:
            print(f"{'':<10} | {'':<40} | {'* SAFETY WARNING *':<25} | {', '.join(safety_issues):<43} | FAIL")

    print("\n" + "=" * 50)
    print(f"Summary: {passed_count}/{total_count} cases passed core rules.")
    print("=" * 50)
    
    if passed_count == total_count:
        print("\nSUCCESS: All sample cases match expected core fields perfectly!")
        sys.exit(0)
    else:
        print("\nWARNING: Some core fields do not match expected outcomes. Please check heuristics.")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
