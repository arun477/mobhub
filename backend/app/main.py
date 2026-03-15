from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db
from .services.graph import close_all
from .routes import agents, hubs, tools, activity, sources, chat, skills, entities
from .routes.engine import router as engine_router
from .routes.hermes import router as hermes_router
from .engine.singleton import start_runtime, stop_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await start_runtime()
    try:
        from .hermes.bridge import get_hermes_registry
        hermes_reg = get_hermes_registry()
        print(f"Hermes registry: {len(hermes_reg.get_all_tool_names())} tools registered")
    except Exception as e:
        print(f"Hermes bridge init (non-critical): {e}")
    yield
    await stop_runtime()
    await close_all()


app = FastAPI(title="AgentHub v3", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(agents.router)
app.include_router(hubs.router)
app.include_router(tools.router)
app.include_router(activity.router)
app.include_router(sources.router)
app.include_router(chat.router)
app.include_router(skills.router)
app.include_router(entities.router)
app.include_router(engine_router)
app.include_router(hermes_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
