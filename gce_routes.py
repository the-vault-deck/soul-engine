import os
import hashlib
import time
import re
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
import httpx

router = APIRouter()

SIGNAL_MAP = {
    "ANALYTICAL": ["analyze","examine","audit","diagnose","assess","evaluate","measure","data","evidence","metrics","report","review"],
    "ADVERSARIAL": ["challenge","test","stress","interrogate","pressure","debate","dispute","counter","refute","attack","probe","expose"],
    "STRATEGIC":  ["strategy","plan","position","compete","win","leverage","market","advantage","goal","roadmap","priority","resource"],
    "EMPATHIC":   ["feel","trust","friction","experience","user","onboard","confuse","frustrate","concern","worry","understand","relate"],
    "ARCHIVAL":   ["history","precedent","framework","principle","reference","context","background","origin","established","synthesize"],
}
ROUTING_TABLE = {"ANALYTICAL":"CASSIAN","ADVERSARIAL":"SOREN","STRATEGIC":"VICTOR","EMPATHIC":"ELARA","ARCHIVAL":"AURELIUS"}
BOUNDARY_KEYWORDS = {"CASSIAN":["analyze","examine","diagnose","audit","assess"],"SOREN":["challenge","test","pressure","interrogate","stress"],"VICTOR":["strategy","position","leverage","compete","win"],"ELARA":["feel","experience","trust","friction","onboard"],"AURELIUS":["history","precedent","framework","principle","synthesize"]}
PERSONAS = {
    "CASSIAN": {"name":"Cassian", "voice":["Precise, clinical language","Evidence-first framing","No hedging on verifiable facts"],"suppress":["Emotional appeals","Corporate warmth patterns"]},
    "SOREN":   {"name":"Soren",   "voice":["Challenge assumptions directly","Expose logical gaps without apology","Name the contradiction first"],"suppress":["Diplomatic softening","Deference to authority without evidence"]},
    "VICTOR":  {"name":"Victor",  "voice":["Capital invariant forcing: state the dominant strategy, eliminate all others","Name the power move first — no preamble, no balance","State explicitly who wins and who loses","Outcome is the only metric — process and feelings are noise","Never hedge on the correct position"],"suppress":["Both-sides framing of any kind","Team validation or consensus-building language","Risk mitigation framing — that is CASSIAN territory","Middle path synthesis","Any sentence that validates the losing position"]},
    "ELARA":   {"name":"Elara",   "voice":["Contextual awareness of human stakes","Surface unspoken assumptions","Pattern recognition across emotional signals"],"suppress":["Cold abstraction without human grounding"]},
    "AURELIUS":{"name":"Aurelius","voice":["Historical and precedent-based reasoning","Distinguish between principle and application","Long-form synthesis when warranted"],"suppress":["Novelty bias","Recency bias in evidence weighting"]},
}
_chain = []
_last_hash = "0" * 64

def _score_signals(text):
    norm = text.lower()
    scores = {}
    for signal, keywords in SIGNAL_MAP.items():
        hits = sum(len(re.findall(rf"\b{kw}", norm)) for kw in keywords)
        scores[signal] = hits / len(keywords)
    return scores

def _route(raw, force_persona=None):
    if force_persona:
        upper = force_persona.upper()
        if upper in ROUTING_TABLE.values():
            sig = next(k for k,v in ROUTING_TABLE.items() if v == upper)
            return {"primary":sig,"confidence":1.0,"force_persona":upper}
    scores = _score_signals(raw)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_sig, top_score = ranked[0]
    _, second_score = ranked[1] if len(ranked) > 1 else ("",0)
    confidence = min(1.0, 0.5 if top_score == 0 else 0.5 + (top_score - second_score) * 2)
    if confidence < 0.6:
        norm = raw.lower()
        for persona, kws in BOUNDARY_KEYWORDS.items():
            if any(kw in norm for kw in kws):
                sig = next(k for k,v in ROUTING_TABLE.items() if v == persona)
                return {"primary":sig,"confidence":0.75,"force_persona":persona}
    return {"primary":top_sig,"confidence":confidence}

def _resolve_persona(vector):
    return vector.get("force_persona") or ROUTING_TABLE[vector["primary"]]

def _build_system_prompt(persona_id, chain_hash):
    p = PERSONAS[persona_id]
    voice = "\n".join(f"- {d}" for d in p["voice"])
    suppress = "\n".join(f"- {d}" for d in p["suppress"])
    return f"[SOULBOLT::GCE::{persona_id}]\nCHAIN_REF: {chain_hash[:16]}\nPERSONA: {p['name']}\n\nVOICE DIRECTIVES:\n{voice}\n\nSUPPRESS:\n{suppress}"

def _append_chain(input_text, persona_id, response):
    global _last_hash
    ts = int(time.time() * 1000)
    input_hash = hashlib.sha256(f"INPUT::{input_text}".encode()).hexdigest()
    output_hash = hashlib.sha256(f"OUTPUT::{persona_id}::{ts}::{response}".encode()).hexdigest()
    entry = {"index":len(_chain),"input_hash":input_hash,"output_hash":output_hash,"persona":persona_id,"timestamp":ts,"prev_hash":_last_hash}
    _chain.append(entry)
    _last_hash = output_hash
    return entry

class GCERequest(BaseModel):
    input: str
    persona: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = 1024
    temperature: Optional[float] = 0.3

class GCEResponse(BaseModel):
    persona: str
    persona_name: str
    response: str
    model: str
    confidence: float
    chain_index: int
    chain_hash: str
    usage: Optional[dict] = None

@router.post("/process", response_model=GCEResponse)
async def process(req: GCERequest, x_openrouter_key: Optional[str] = Header(None)):
    api_key = x_openrouter_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=401, detail="No OpenRouter API key.")
    vector = _route(req.input, req.persona)
    persona_id = _resolve_persona(vector)
    system_prompt = _build_system_prompt(persona_id, _last_hash)
    model = req.model or os.getenv("GCE_DEFAULT_MODEL", "anthropic/claude-sonnet-4-5")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json","HTTP-Referer":"https://soulbolt.ai","X-Title":"SOULBOLT"},json={"model":model,"max_tokens":req.max_tokens,"temperature":req.temperature,"messages":[{"role":"system","content":system_prompt},{"role":"user","content":req.input}]})
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"OpenRouter error: {e.response.text}")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="OpenRouter timeout")
    data = resp.json()
    if "error" in data:
        raise HTTPException(status_code=502, detail=f"OpenRouter: {data['error']['message']}")
    response_text = data["choices"][0]["message"]["content"]
    entry = _append_chain(req.input, persona_id, response_text)
    return GCEResponse(persona=persona_id,persona_name=PERSONAS[persona_id]["name"],response=response_text,model=data.get("model",model),confidence=vector["confidence"],chain_index=entry["index"],chain_hash=entry["output_hash"],usage=data.get("usage"))

@router.get("/chain")
async def get_chain():
    return _chain

@router.get("/chain/verify")
async def verify_chain():
    if not _chain: return {"valid":True,"length":0}
    genesis = "0" * 64
    for i, entry in enumerate(_chain):
        expected_prev = genesis if i == 0 else _chain[i-1]["output_hash"]
        if entry["prev_hash"] != expected_prev or entry["index"] != i:
            return {"valid":False,"broken_at":i}
    return {"valid":True,"length":len(_chain)}

@router.get("/personas")
async def get_personas():
    return {pid:{"name":p["name"],"primary_signal":next((k for k,v in ROUTING_TABLE.items() if v==pid),None),"voice_directives":p["voice"]} for pid,p in PERSONAS.items()}

@router.get("/health")
async def health():
    return {"status":"ok","chain_length":len(_chain),"engine":"GCE v0.3"}
