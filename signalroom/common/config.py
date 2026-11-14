"""Model provider configuration (ARCHITECTURE.md sections 3.6 and 15)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderConfig(_Config):
    name: str
    base_url: str
    model: str
    api_key_env: str | None = None
    timeout_s: float = 60
    price_in_per_m: float = Field(default=0, ge=0)
    price_out_per_m: float = Field(default=0, ge=0)

    def cost_usd(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.price_in_per_m + tokens_out * self.price_out_per_m) / 1_000_000


class RoleConfig(_Config):
    temperature: float = 0
    max_output_tokens: int = Field(default=1000, gt=0)
    providers: list[ProviderConfig] = Field(min_length=1)


class BudgetConfig(_Config):
    daily_requests: int = Field(gt=0)
    daily_tokens: int = Field(gt=0)
    daily_usd: float = Field(gt=0)


class ModelsConfig(_Config):
    budget: BudgetConfig
    roles: dict[str, RoleConfig]


def load_config(path: str | Path) -> ModelsConfig:
    with open(path) as f:
        return ModelsConfig.model_validate(yaml.safe_load(f))
