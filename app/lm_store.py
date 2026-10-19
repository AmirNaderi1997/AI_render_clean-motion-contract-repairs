"""AI configuration and audit persistence; PostgreSQL in production, local JSON in dev."""
from __future__ import annotations
import asyncio
import copy
import json
import threading
from pathlib import Path
from sqlalchemy import select, func
from app.config import settings
from app.database import AsyncSessionLocal, DB_AVAILABLE
from app.models import AIModel, AIModelRoute, AIGatewaySettings, AIRequestLog

_lock = threading.RLock()
TABLES = {"models": AIModel, "routes": AIModelRoute, "settings": AIGatewaySettings}


def _path():
    return Path(settings.JOBS_DIR) / "ai_gateway" / "state.json"


def _read():
    path = _path()
    return json.loads(path.read_text()) if path.exists() else {"models": {}, "routes": {}, "settings": {}, "logs": {}}


def _write(data):
    path = _path(); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp"); tmp.write_text(json.dumps(data, ensure_ascii=False)); tmp.replace(path)


async def _records(table):
    if DB_AVAILABLE:
        async with AsyncSessionLocal() as db:
            return {row.key: copy.deepcopy(row.data) for row in (await db.execute(select(TABLES[table]))).scalars()}
    with _lock:
        return copy.deepcopy(_read()[table])


async def _save(table, rows):
    if DB_AVAILABLE:
        async with AsyncSessionLocal() as db:
            for key, data in rows.items():
                await db.merge(TABLES[table](key=key, data=data))
            await db.commit()
    else:
        with _lock:
            data = _read(); data[table].update(copy.deepcopy(rows)); _write(data)


def records(table):
    return asyncio.run(_records(table))


def save(table, rows):
    asyncio.run(_save(table, rows))


async def _patch(table, key, changes, union):
    if DB_AVAILABLE:
        async with AsyncSessionLocal() as db:
            row = await db.scalar(select(TABLES[table]).where(TABLES[table].key==key).with_for_update())
            current = copy.deepcopy(row.data) if row else {}
            value = {**current, **changes}
            for field in union: value[field] = sorted(set(current.get(field,[])) | set(changes.get(field,[])))
            if row: row.data = value
            else: db.add(TABLES[table](key=key,data=value))
            await db.commit(); return value
    with _lock:
        data=_read(); current=data[table].get(key,{})
        value={**current,**copy.deepcopy(changes)}
        for field in union:value[field]=sorted(set(current.get(field,[]))|set(changes.get(field,[])))
        data[table][key]=value;_write(data);return copy.deepcopy(value)


def patch(table, key, changes, union=()):
    return asyncio.run(_patch(table,key,changes,union))


async def _log(value):
    if DB_AVAILABLE:
        async with AsyncSessionLocal() as db:
            await db.merge(AIRequestLog(id=value["id"], created_at=value["timestamp"], route=value["route"],
                user_id=value.get("user_id"), job_id=value.get("job_id"), status=value["status"],
                model=value["requested_model"], data=value))
            await db.commit()
    else:
        with _lock:
            data = _read(); data["logs"][value["id"]] = value; _write(data)


def log(value):
    asyncio.run(_log(value))


async def _logs(filters, page, size):
    if DB_AVAILABLE:
        conditions = []
        for key, column in (("id", AIRequestLog.id), ("model", AIRequestLog.model),
                            ("status", AIRequestLog.status), ("user_id", AIRequestLog.user_id),
                            ("route", AIRequestLog.route)):
            if filters.get(key): conditions.append(column == filters[key])
        if filters.get("since"): conditions.append(AIRequestLog.created_at >= filters["since"])
        if filters.get("until"): conditions.append(AIRequestLog.created_at <= filters["until"])
        async with AsyncSessionLocal() as db:
            total = await db.scalar(select(func.count()).select_from(AIRequestLog).where(*conditions))
            query = select(AIRequestLog).where(*conditions).order_by(AIRequestLog.created_at.desc()).offset((page-1)*size).limit(size)
            return {"items": [row.data for row in (await db.execute(query)).scalars()], "total": total}
    with _lock:
        values = list(_read()["logs"].values())
    for key, field in (("id", "id"), ("model", "requested_model"), ("status", "status"), ("user_id", "user_id"), ("route", "route")):
        if filters.get(key): values = [v for v in values if v.get(field) == filters[key]]
    if filters.get("since"): values = [v for v in values if v["timestamp"] >= filters["since"]]
    if filters.get("until"): values = [v for v in values if v["timestamp"] <= filters["until"]]
    values.sort(key=lambda v: v["timestamp"], reverse=True)
    return {"items": values[(page-1)*size:page*size], "total": len(values)}


def logs(filters=None, page=1, size=50):
    return asyncio.run(_logs(filters or {}, page, size))
