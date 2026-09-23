from fastapi import FastAPI

app = FastAPI(title="Token Optimization Framework")


@app.get("/health")
def health_check():
    return {"status": "ok"}
