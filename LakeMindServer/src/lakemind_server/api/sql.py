from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


def _eng(request: Request):
    return request.app.state.engines.sql


class SqlBody(BaseModel):
    sql: str
    tables: dict | None = None


@router.post("/")
async def execute_sql(body: SqlBody, request: Request):
    import pyarrow as pa
    tables = None
    if body.tables:
        tables = {k: pa.Table.from_pylist(v) for k, v in body.tables.items()}
    results = await asyncio.to_thread(_eng(request).execute, body.sql, tables)
    return {"results": results, "count": len(results)}
