from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.integrations.storage.base import ObjectStorage


@lru_cache
def get_storage() -> ObjectStorage:
    s = get_settings()
    if s.storage_backend == "supabase":
        from app.integrations.storage.supabase import SupabaseStorage

        if not (s.supabase_url and s.supabase_secret_key):
            raise RuntimeError("STORAGE_BACKEND=supabase requires SUPABASE_URL and SUPABASE_SECRET_KEY")
        return SupabaseStorage(s.supabase_url, s.supabase_secret_key.get_secret_value(), s.storage_bucket_resumes)
    from app.integrations.storage.local import LocalStorage

    return LocalStorage(s.local_storage_dir)
