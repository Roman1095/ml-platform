from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.db.session import get_db
from app.api.routes.datasets import router as datasets_router
from app.api.routes.templates import router as templates_router
from app.api.routes.jobs import router as jobs_router

app = FastAPI(
    title="ML Training Platform",
    version="0.1.0",
)


# app.include_router(auth_router)
# app.include_router(users_router)
app.include_router(jobs_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(templates_router)
app.include_router(datasets_router)

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


@app.get("/api/health/db")
async def database_health(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            """
            SELECT
                current_database(),
                current_user
            """
        )
    )

    database_name, database_user = result.one()

    return {
        "status": "healthy",
        "database": database_name,
        "user": database_user,
    }


@app.get("/api/health/db/tables")
async def database_tables(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
    )

    tables = [row[0] for row in result.all()]

    return {
        "status": "healthy",
        "tables": tables,
    }