from fastapi import FastAPI
from api.db.main import init_db
from contextlib import asynccontextmanager
from api.auth.routes import router as auth_router
from api.posts.routes import router as posts_router
from api.comments.routes import router as comments_router
from api.votes.routes import router as votes_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

version = "v1"

app = FastAPI(title="chefly", version=version, description="A simple API for a cooking recipe sharing and voting", lifespan=lifespan)

app.get("/")(lambda: {"message": "Hello World"})

app.get("/health")(lambda: {"status": "ok"})

app.include_router(auth_router)
app.include_router(posts_router)
app.include_router(comments_router)
app.include_router(votes_router)