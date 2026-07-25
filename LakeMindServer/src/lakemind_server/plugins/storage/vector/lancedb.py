from __future__ import annotations
from typing import Any
import threading
import pyarrow as pa
import lancedb


class LanceVectorStorage:
    def __init__(self, uri: str, **kwargs):
        self._uri = uri
        self._conns: dict[str, Any] = {}
        self._tables: dict[str, Any] = {}
        self._table_locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def _conn(self, db: str):
        if db not in self._conns:
            self._conns[db] = lancedb.connect(f"{self._uri}/{db}")
        return self._conns[db]

    def _get_lock(self, db: str, name: str) -> threading.Lock:
        key = f"{db}/{name}"
        with self._meta_lock:
            if key not in self._table_locks:
                self._table_locks[key] = threading.Lock()
            return self._table_locks[key]

    def _table(self, db: str, name: str):
        key = f"{db}/{name}"
        if key not in self._tables:
            self._tables[key] = self._conn(db).open_table(name)
        return self._tables[key]

    def _invalidate(self, db: str, name: str):
        key = f"{db}/{name}"
        self._tables.pop(key, None)

    def create_table(self, db: str, name: str, data: pa.Table, mode: str = "overwrite") -> None:
        lock = self._get_lock(db, name)
        with lock:
            self._conn(db).create_table(name, data=data, mode=mode)
            self._invalidate(db, name)

    def table_exists(self, db: str, name: str) -> bool:
        return name in self.list_tables(db)

    def list_tables(self, db: str) -> list[str]:
        with self._meta_lock:
            try:
                return self._conn(db).table_names()
            except Exception:
                return []

    def add(self, db: str, name: str, data: pa.Table) -> int:
        lock = self._get_lock(db, name)
        with lock:
            tbl = self._conn(db).open_table(name)
            tbl.add(data)
            self._invalidate(db, name)
            return data.num_rows

    def search(self, db: str, name: str, query_vec: list[float],
               top_k: int = 5, filter: str | None = None) -> list[dict]:
        lock = self._get_lock(db, name)
        with lock:
            tbl = self._table(db, name)
            q = tbl.search(query_vec).limit(top_k)
            if filter:
                q = q.where(filter)
            return q.to_list()

    def count_rows(self, db: str, name: str) -> int:
        lock = self._get_lock(db, name)
        with lock:
            try:
                return self._table(db, name).count_rows()
            except Exception:
                return 0

    def describe(self, db: str, name: str) -> dict:
        lock = self._get_lock(db, name)
        with lock:
            tbl = self._table(db, name)
            row_count = tbl.count_rows()
            return {
                "name": name,
                "row_count": row_count,
                "concept_count": row_count,
                "schema": tbl.schema.names,
            }

    def scan(self, db: str, name: str, limit: int = 100, offset: int = 0) -> list[dict]:
        lock = self._get_lock(db, name)
        with lock:
            tbl = self._table(db, name)
            arrow_tbl = tbl.to_arrow()
            total = arrow_tbl.num_rows
            start = min(offset, total)
            end = min(offset + limit, total)
            sliced = arrow_tbl.slice(start, end - start)
            return sliced.to_pylist()

    def health(self) -> bool:
        with self._meta_lock:
            try:
                lancedb.connect(self._uri)
                return True
            except Exception:
                return False

    def create_index(self, db: str, name: str, vector_column: str = "vector",
                     index_type: str = "IVF_PQ", num_partitions: int = 128,
                     num_sub_vectors: int = 16) -> dict:
        lock = self._get_lock(db, name)
        with lock:
            tbl = self._table(db, name)
            tbl.create_index(
                metric="L2",
                vector_column_name=vector_column,
                num_partitions=num_partitions,
                num_sub_vectors=num_sub_vectors,
                replace=True,
            )
            return {
                "db": db, "table": name, "index_type": index_type,
                "num_partitions": num_partitions, "num_sub_vectors": num_sub_vectors,
                "status": "active", "indexed_rows": tbl.count_rows(),
            }

    def list_indexes(self, db: str, name: str) -> list[dict]:
        lock = self._get_lock(db, name)
        with lock:
            tbl = self._table(db, name)
            try:
                idx_stats = tbl.list_indices()
                return [
                    {
                        "name": getattr(s, "name", f"idx_{i}"),
                        "columns": getattr(s, "columns", []),
                        "index_type": getattr(s, "index_type", "IVF_PQ"),
                    }
                    for i, s in enumerate(idx_stats)
                ]
            except Exception:
                return []

    def drop_index(self, db: str, name: str, index_name: str = "vector_idx") -> dict:
        lock = self._get_lock(db, name)
        with lock:
            tbl = self._table(db, name)
            try:
                tbl.drop_index(index_name)
                return {"status": "dropped", "index_name": index_name}
            except Exception:
                return {"status": "not_found", "index_name": index_name}
