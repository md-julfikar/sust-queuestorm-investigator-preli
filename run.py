import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"Starting QueueStorm Investigator service on {settings.HOST}:{settings.PORT}...")
    print(f"Debug Mode: {settings.DEBUG}")
    if settings.GEMINI_API_KEY:
        print("Gemini API Key is configured. LLM analysis will be active.")
    else:
        print("No Gemini API Key found. Service will run in LOCAL HEURISTIC mode.")

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
