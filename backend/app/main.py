from fastapi import FastAPI


app = FastAPI(
    title="ML Training Platform",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {
        "service": "ML Training Platform",
        "status": "ok",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }