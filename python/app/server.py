from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Config, Model


class Health(Model):
    status: str = "ok"
    service: str = "simulation-backend"
    api_version: str = "1"
    simulation_active: bool = False
    simulation_id: str | None = None


ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
app = FastAPI(title="Trustless Mixnet DHT Messaging Simulator")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET","POST","PUT"],
                   allow_headers=["Content-Type"])


@app.get("/health")
def health() -> Health:
    return Health()


@app.get("/api/config")
def defaults() -> Config:
    return Config()


class Info(Model):
    api_version: str = "1"
    port: int | None
    capabilities: list[str]
    protocols: list[dict] = []


@app.get("/api/info")
def info() -> Info:
    return Info(port=getattr(app.state, "port", None), capabilities=["configuration"])
