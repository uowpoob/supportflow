def main() -> None:
    """Start the local development API."""
    import uvicorn

    uvicorn.run("supportflow.main:app", host="127.0.0.1", port=8000)
