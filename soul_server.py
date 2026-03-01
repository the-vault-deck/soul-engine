print(">>> SOUL SERVER LOADING <<<")
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict

from soul_core import Soul
from gce_routes import router as gce_router
print(">>> Soul import succeeded <<<")

print(">>> Creating FastAPI app <<<")
app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

print(">>> FastAPI app created <<<")
app.include_router(gce_router, prefix="/gce", tags=["GCE"])

# =========================
# IN-MEMORY SOUL REGISTRY
# =========================

souls: Dict[str, Soul] = {}


# =========================
# REQUEST MODELS
# =========================

class CreateSoulRequest(BaseModel):
    soul_id: str | None = None
    promotion_threshold: int = 3


class FlagRequest(BaseModel):
    key: str
    value: str


class SaveRequest(BaseModel):
    filename: str


class LoadRequest(BaseModel):
    filename: str
    soul_name: str


# =========================
# ROUTES
# =========================

@app.post("/soul/create")
def create_soul(req: CreateSoulRequest):
    soul = Soul(promotion_threshold=req.promotion_threshold)

    name = req.soul_id or soul.soul_id
    souls[name] = soul

    return {
        "message": "Soul created",
        "soul_name": name,
        "public_key": soul.public_key
    }


@app.post("/soul/{soul_name}/flag")
def flag_memory(soul_name: str, req: FlagRequest):
    if soul_name not in souls:
        raise HTTPException(status_code=404, detail="Soul not found")

    soul = souls[soul_name]
    soul.flag_candidate(req.key, req.value)

    return {
        "message": "Flag processed",
        "hot_memory": soul.hot_memory
    }


@app.get("/soul/{soul_name}/hot")
def get_hot_memory(soul_name: str):
    if soul_name not in souls:
        raise HTTPException(status_code=404, detail="Soul not found")

    return souls[soul_name].hot_memory


@app.get("/soul/{soul_name}/verify")
def verify_soul(soul_name: str):
    if soul_name not in souls:
        raise HTTPException(status_code=404, detail="Soul not found")

    return {
        "chain_valid": souls[soul_name].verify_chain()
    }


@app.post("/soul/{soul_name}/save")
def save_soul(soul_name: str, req: SaveRequest):
    if soul_name not in souls:
        raise HTTPException(status_code=404, detail="Soul not found")

    souls[soul_name].save_to_disk(req.filename)

    return {"message": "Soul saved"}


@app.post("/soul/load")
def load_soul(req: LoadRequest):
    soul = Soul.load_from_disk(req.filename)
    souls[req.soul_name] = soul


    return {"message": "Soul loaded", "soul_name": req.soul_name}
