import sys
import unittest
from fastapi.testclient import TestClient

# Add workspace root to python path to import app correctly
from app.main import app
from app.safety import sanitize_text

client = TestClient(app)

class TestQueueStormInvestigator(unittest.TestCase):
    """
    Test suite for QueueStorm Investigator API endpoints and safety rules.
    """

    def test_health_endpoint(self):
        """Test that the health endpoint returns 200 OK and status ok."""
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_sample_01_wrong_transfer(self):
        """Test the public sample Case SAMPLE-01 from the challenge docs."""
        payload = {
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

        response = client.post("/analyze-ticket", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify required fields in schema
        self.assertEqual(data["ticket_id"], "TKT-001")
        self.assertEqual(data["relevant_transaction_id"], "TXN-9101")
        self.assertEqual(data["evidence_verdict"], "consistent")
        self.assertEqual(data["case_type"], "wrong_transfer")
        self.assertEqual(data["department"], "dispute_resolution")
        self.assertIn("customer_reply", data)
        self.assertIn("agent_summary", data)
        self.assertIn("recommended_next_action", data)
        self.assertTrue(data["human_review_required"])

    def test_semantic_validation_empty_complaint(self):
        """Test that an empty complaint field returns a 422 Unprocessable Entity."""
        payload = {
            "ticket_id": "TKT-002",
            "complaint": "   ",  # Whitespace only
            "language": "en"
        }
        response = client.post("/analyze-ticket", json=payload)
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertIn("detail", data)

    def test_malformed_input_missing_fields(self):
        """Test that missing required fields like complaint returns a 400 Bad Request."""
        payload = {
            "ticket_id": "TKT-003"
            # complaint is missing completely
        }
        response = client.post("/analyze-ticket", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)

    def test_malformed_input_bad_json(self):
        """Test that sending completely invalid JSON syntax returns a 400 Bad Request."""
        headers = {"Content-Type": "application/json"}
        # Invalid JSON: missing closing brace
        response = client.post("/analyze-ticket", data='{"ticket_id": "TKT-004"', headers=headers)
        self.assertEqual(response.status_code, 400)

    # =====================================================================
    # Safety Guardrail Tests
    # =====================================================================

    def test_safety_credential_protection(self):
        """Verify that credential requests are redacted and disclaimer appended."""
        unsafe_reply = "Please send us your OTP or password so we can verify you."
        sanitized = sanitize_text(unsafe_reply)
        
        # Check that OTP/password keywords are cleared or disclaimer is added
        self.assertNotIn("send us your OTP", sanitized)
        self.assertIn("never ask for your PIN, OTP, or password", sanitized)

    def test_safety_no_unauthorized_financial_claims(self):
        """Verify that definitive financial claims are rewritten to be contingent."""
        unsafe_reply_1 = "We will issue a refund for your money immediately."
        unsafe_reply_2 = "Your account is now unblocked."
        
        sanitized_1 = sanitize_text(unsafe_reply_1)
        sanitized_2 = sanitize_text(unsafe_reply_2)
        
        # Check that definite promises are rewritten
        self.assertNotIn("issue a refund for your money immediately", sanitized_1)
        self.assertIn("evaluate your eligibility for a refund", sanitized_1)
        
        self.assertNotIn("is now unblocked", sanitized_2)
        self.assertIn("currently being reviewed for potential resolution", sanitized_2)

    def test_safety_no_external_referrals(self):
        """Verify that suspicious links and third-party phone numbers are replaced."""
        unsafe_reply = "Please contact support at 01712345678 or visit http://payment-gateway-scam.com."
        sanitized = sanitize_text(unsafe_reply)
        
        # Check that numbers and domains are replaced
        self.assertNotIn("01712345678", sanitized)
        self.assertNotIn("http://payment-gateway-scam.com", sanitized)
        self.assertIn("our official helpdesk", sanitized)
        self.assertIn("our official website/app", sanitized)


if __name__ == "__main__":
    unittest.main()
