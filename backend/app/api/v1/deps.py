from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.adapters.fx_ecb import make_fetcher
from app.core.auth import WRITE_ROLES, Principal, require_role
from app.core.settings import get_settings
from app.domain.fx.service import FxService

WriterDep = Annotated[Principal, Depends(require_role(*WRITE_ROLES))]


@lru_cache(maxsize=1)
def get_fx_service() -> FxService:
    return FxService(make_fetcher(get_settings().fx_api_url))


FxDep = Annotated[FxService, Depends(get_fx_service)]
