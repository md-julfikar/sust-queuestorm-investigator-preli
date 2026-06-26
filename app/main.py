import logging
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder

from app.models import TicketAnalysisRequest, TicketAnalysisResponse
from app.analyzer import analyze_ticket_investigator

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(
    title="QueueStorm Investigator API",
    description="AI/API SupportOps Copilot service for analyzing customer tickets.",
    version="1.0.0"
)

# Enable CORS for convenience
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================================
# Custom Exception Handlers
# =====================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Translates schema validation errors to comply with HTTP status definitions:
    - 400 for structural issues (missing required fields, bad types, invalid JSON syntax).
    - 422 for semantic validity issues (empty complaint text, negative amounts, etc.).
    """
    errors = jsonable_encoder(exc.errors())
    logger.warning(f"Validation error occurred: {errors}")
    
    is_structural_or_malformed = False
    
    for err in errors:
        err_type = err.get("type", "")
        # Pydantic v2 error types:
        # - 'missing': field not provided.
        # - 'json_invalid': request body is not valid json.
        # - '*_type': type mismatch (e.g. string expected but got int/dict).
        if err_type in ("missing", "json_invalid") or "type" in err_type or "parsing" in err_type:
            is_structural_or_malformed = True
            break
            
    if is_structural_or_malformed:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": "Malformed input (invalid JSON or missing required structural fields)",
                "errors": errors
            }
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Schema valid, but input is semantically invalid (e.g., empty complaint text)",
                "errors": errors
            }
        )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches all unexpected internal errors.
    Returns a generic 500 message to avoid leaking stack traces or sensitive data keys.
    """
    logger.error(f"Unhandled exception at {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred."
        }
    )

# =====================================================================
# Routes
# =====================================================================

@app.get("/health")
async def health_check():
    """
    Service health check endpoint.
    """
    return {"status": "ok"}

@app.post("/analyze-ticket", response_model=TicketAnalysisResponse)
async def analyze_ticket(request: TicketAnalysisRequest):
    """
    Main ticket investigator endpoint.
    Cross-references complaint text and recent transaction history.
    """
    logger.info(f"Received ticket analysis request for ticket_id: {request.ticket_id}")
    
    # Process the ticket analysis
    response = await analyze_ticket_investigator(request)
    
    logger.info(f"Successfully completed analysis for ticket_id: {request.ticket_id}")
    return response
