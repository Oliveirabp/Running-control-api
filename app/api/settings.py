from fastapi import APIRouter, Depends

from app.api.deps import get_config
from app.schemas import SettingsOut
from app.services.config_store import AppConfig

router = APIRouter(prefix="/settings", tags=["Configurações"])


@router.get("", response_model=SettingsOut)
def read_settings(cfg: AppConfig = Depends(get_config)):
    return SettingsOut(
        threshold_min=cfg.threshold_min,
        aging_options_h=list(cfg.aging_options_h),
        group_capacity=list(cfg.layout.group_capacity),
        rows_per_side=cfg.layout.rows_per_side,
        lines=sorted(cfg.lines),
        reasons=list(cfg.reasons),
        baseline_min=cfg.baseline_min,
        baseline_fonte=cfg.baseline_fonte,
    )
