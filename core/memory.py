import os
import json
import time
import uuid
import re
import logging
import asyncio
from typing import List, Dict, Any

from providers import ProviderFactory

import warnings

try:
    # Suppress LanceDB fork-safety warning
    warnings.filterwarnings("ignore", message=".*lance is not fork-safe.*")
    import lancedb

    LANCE_AVAILABLE = True
except ImportError:
    LANCE_AVAILABLE = False


class MemoryManager:
    def __init__(self, db_dir: str = None, provider_name: str = "ollama"):
        if db_dir is None:
            # Default to a global user directory so that memories/RAG are shared across different projects.
            db_dir = os.path.expanduser("~/.mini_cli/lancedb")
        self.db_dir = db_dir
        self.provider_name = provider_name
        self.provider = ProviderFactory.get_provider(provider_name)
        self._db = None
        self._table = None
        self.table_name = "error_healing_memory"

    def _init_db(self) -> bool:
        if not LANCE_AVAILABLE:
            return False
        try:
            if self._db is None:
                db_path = os.path.abspath(self.db_dir)
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                self._db = lancedb.connect(db_path)

            # Check if table exists
            tables = self._db.list_tables()
            table_list = tables.tables if hasattr(tables, "tables") else tables
            if self.table_name in table_list:
                self._table = self._db.open_table(self.table_name)
            else:
                # Create table with a dummy initial record to define the schema.
                # Try to generate an embedding vector for the dummy to establish the schema.
                dummy_emb = self.provider.embed("dummy")
                dummy_data = {
                    "id": str(uuid.uuid4()),
                    "task_description": "dummy",
                    "error_log": "dummy error",
                    "solution": json.dumps([]),
                    "timestamp": time.time(),
                }
                if dummy_emb:
                    dummy_data["vector"] = dummy_emb
                self._table = self._db.create_table(self.table_name, data=[dummy_data])
            return True
        except Exception as e:
            logging.warning(f"Failed to initialize LanceDB memory: {e}")
            return False

    async def add_memory(
        self, task_description: str, error_log: str, modifications: List[Any]
    ) -> bool:
        """Saves a successfully resolved error-solution pair to LanceDB, updating existing similar entries."""
        loop = asyncio.get_event_loop()
        initialized = await loop.run_in_executor(None, self._init_db)
        if not initialized or not self._table:
            return False

        try:
            # Format modifications to a serializable dict list
            mods_data = []
            for m in modifications:
                mods_data.append(
                    {
                        "filepath": getattr(m, "filepath", ""),
                        "content": getattr(m, "content", ""),
                    }
                )

            # Scrub sensitive information (Secrets, Passwords, etc.)
            safe_error = self._redact_secrets(error_log)
            safe_task = self._redact_secrets(task_description)

            # Generate embedding vector for the new entry
            embedding = await loop.run_in_executor(
                None, self.provider.embed, safe_error
            )

            def process_and_add():
                schema = self._table.schema
                has_vector_col = "vector" in schema.names

                # Check if we should upgrade the table schema to support vectors
                if embedding and not has_vector_col:
                    logging.info(
                        "Upgrading memory table schema to include vector embeddings..."
                    )
                    df = self._table.to_pandas()
                    records = df.to_dict(orient="records")
                    for r in records:
                        r["vector"] = self.provider.embed(r["error_log"])
                    self._table = self._db.create_table(
                        self.table_name, data=records, mode="overwrite"
                    )
                    has_vector_col = True

                # Check for duplicate error log using Jaccard keyword overlap (fallback/deduplication)
                # Load only required columns to save memory and CPU
                df_meta = (
                    self._table.search()
                    .select(["id", "task_description", "error_log"])
                    .to_pandas()
                )
                records = df_meta.to_dict(orient="records")

                new_keywords = self._extract_keywords(safe_error)
                duplicate_id = None
                for r in records:
                    if r["task_description"] == "dummy":
                        continue
                    rec_keywords = self._extract_keywords(r["error_log"])
                    if new_keywords and rec_keywords:
                        intersection = new_keywords.intersection(rec_keywords)
                        overlap = len(intersection) / len(
                            new_keywords.union(rec_keywords)
                        )
                        if overlap > 0.85:
                            duplicate_id = r["id"]
                            break

                if duplicate_id is not None:
                    # Update existing record using LanceDB native update operation
                    values = {
                        "solution": json.dumps(mods_data),
                        "timestamp": time.time(),
                        "task_description": safe_task,
                    }
                    if embedding and has_vector_col:
                        values["vector"] = embedding

                    # Validate ID format strictly against UUID/safe identifier regex
                    if re.match(r"^[a-fA-F0-9\-]+$", duplicate_id):
                        self._table.update(where=f"id = '{duplicate_id}'", values=values)
                    else:
                        escaped_id = duplicate_id.replace("'", "''").replace("\\", "\\\\")
                        self._table.update(where=f"id = '{escaped_id}'", values=values)
                else:
                    # Append new record using LanceDB native add operation
                    new_rec = {
                        "id": str(uuid.uuid4()),
                        "task_description": safe_task,
                        "error_log": safe_error,
                        "solution": json.dumps(mods_data),
                        "timestamp": time.time(),
                    }
                    if embedding and has_vector_col:
                        new_rec["vector"] = embedding
                    self._table.add([new_rec])

            await loop.run_in_executor(None, process_and_add)
            return True
        except Exception as e:
            logging.warning(f"Failed to add memory to LanceDB: {e}")
            return False

    async def find_relevant_memories(
        self, error_log: str, limit: int = 2
    ) -> List[Dict[str, Any]]:
        """Searches LanceDB for similar past errors using semantic vector search or keyword Jaccard fallback."""
        loop = asyncio.get_event_loop()
        initialized = await loop.run_in_executor(None, self._init_db)
        if not initialized or not self._table:
            return []

        try:
            # Try semantic search first
            embedding = await loop.run_in_executor(None, self.provider.embed, error_log)
            if embedding:
                try:
                    schema = self._table.schema
                    if "vector" in schema.names:
                        # Perform vector search using cosine similarity
                        # LanceDB search returns similarity results directly
                        search_results = (
                            self._table.search(embedding)
                            .metric("cosine")
                            .limit(limit + 1)
                            .to_pandas()
                        )
                        results = []
                        current_time = time.time()

                        for _, row in search_results.iterrows():
                            if row["task_description"] == "dummy":
                                continue
                            try:
                                solution_mods = json.loads(row["solution"])
                            except json.JSONDecodeError as jde:
                                logging.warning(
                                    f"Failed to parse memory solution JSON: {jde}"
                                )
                                solution_mods = []

                            # Convert score (distance) to a similarity score (cosine distance is [0, 2], so similarity is 1 - distance/2)
                            distance = row.get("_distance", 1.0)
                            similarity = max(0.0, 1.0 - (distance / 2.0))

                            # Apply exponential recency decay (30 days half-life)
                            age_days = (
                                current_time - row.get("timestamp", current_time)
                            ) / 86400.0
                            decay = 0.5 ** (age_days / 30.0)

                            results.append(
                                {
                                    "task_description": row["task_description"],
                                    "error_log": row["error_log"],
                                    "solution": solution_mods,
                                    "score": similarity * decay,
                                }
                            )

                        # Filter by minimum score and sort
                        results = [r for r in results if r["score"] > 0.05]
                        results.sort(key=lambda x: x["score"], reverse=True)
                        return results[:limit]
                except Exception as e:
                    logging.info(
                        f"Vector search failed: {e}. Falling back to Jaccard keyword matching."
                    )

            # Fallback to Keyword Jaccard Similarity Match
            def get_records():
                # Load only required columns (avoiding heavy vector embeddings column)
                df_meta = (
                    self._table.search()
                    .select(
                        ["id", "task_description", "error_log", "solution", "timestamp"]
                    )
                    .to_pandas()
                )
                return df_meta.to_dict(orient="records")

            records = await loop.run_in_executor(None, get_records)

            # Remove dummy record
            records = [r for r in records if r["task_description"] != "dummy"]
            if not records:
                return []

            # Calculate similarity score based on keyword overlap
            query_keywords = self._extract_keywords(error_log)
            if not query_keywords:
                return []

            scored_records = []
            current_time = time.time()
            for r in records:
                rec_keywords = self._extract_keywords(r["error_log"])
                if not rec_keywords:
                    overlap = 0.0
                else:
                    intersection = query_keywords.intersection(rec_keywords)
                    overlap = len(intersection) / len(
                        query_keywords.union(rec_keywords)
                    )

                # Apply exponential recency decay (30 days half-life)
                age_days = (current_time - r.get("timestamp", current_time)) / 86400.0
                decay = 0.5 ** (age_days / 30.0)

                scored_records.append((r, overlap * decay))

            # Filter by overlap score > 0.05 and sort
            scored_records = [item for item in scored_records if item[1] > 0.05]
            scored_records.sort(key=lambda x: x[1], reverse=True)

            results = []
            for r, score in scored_records[:limit]:
                try:
                    solution_mods = json.loads(r["solution"])
                except json.JSONDecodeError as jde:
                    logging.warning(
                        f"Failed to parse fallback memory solution JSON: {jde}"
                    )
                    solution_mods = []
                results.append(
                    {
                        "task_description": r["task_description"],
                        "error_log": r["error_log"],
                        "solution": solution_mods,
                        "score": score,
                    }
                )
            return results
        except Exception as e:
            logging.warning(f"Failed to query LanceDB memory: {e}")
            return []

    def _redact_secrets(self, text: str) -> str:
        """Redacts potentially sensitive API keys or passwords from logged error details."""
        pattern = r'(api[_-]?key|secret|password|token|auth)\s*[:=]\s*["\'][^"\']+["\']'
        return re.sub(pattern, r'\1: "***MASKED***"', text, flags=re.IGNORECASE)

    def _extract_keywords(self, text: str) -> set:
        """Cleans and extracts meaningful keywords from error messages."""
        words = re.findall(r"\b[a-zA-Z_]{3,}\b", text.lower())
        stopwords = {
            "the",
            "and",
            "but",
            "with",
            "for",
            "from",
            "error",
            "failed",
            "exception",
            "traceback",
            "file",
            "line",
            "exception",
            "during",
            "module",
            "import",
            "class",
        }
        return {w for w in words if w not in stopwords}
