import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from a .env file if it exists
load_dotenv(dotenv_path=BASE_DIR / ".env")

class Config:
    """
    Configuration settings for the QueueStorm Investigator service.
    Values are loaded from environment variables with sensible defaults.
    """
    # FastAPI configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    # API Keys & LLM configuration
    # Can be configured in the OS environment or in a .env file.
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    
    # Model to use for the analysis.
    # Defaulting to gemini-2.5-flash as the standard fast text model.
    # Supported fallbacks: gemini-1.5-flash, gemini-2.0-flash-exp, etc.
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Timeout for LLM requests in seconds
    REQUEST_TIMEOUT_SEC: float = float(os.getenv("REQUEST_TIMEOUT_SEC", "15.0"))

# Create a singleton configuration instance
settings = Config()
