"""合并 API / 粘贴 / 本地库，解析令牌明文秘钥。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .token_key_import import merge_pasted_keys, parse_pasted_token_keys
from .token_key_vault import load_site_keys, save_token_key


def is_masked_key(raw_key: str) -> bool:
    return "***" in str(raw_key or "")


@dataclass
class TokenKeyResolver:
    base_url: str
    user_id: int | None = None
    by_id: dict[int, str] = field(default_factory=dict)
    by_name: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        *,
        base_url: str,
        user_id: int | None = None,
    ) -> TokenKeyResolver:
        resolver = cls(base_url=base_url, user_id=user_id)
        resolver._load_sources()
        return resolver

    def _load_sources(self) -> None:
        vault_id, vault_name = load_site_keys(self.base_url)
        self._merge(vault_id, vault_name)
        if vault_id or vault_name:
            self.sources.append("local_vault")

    def load_pasted_keys(self, pasted_text: str, tokens: list[dict]) -> None:
        parsed = parse_pasted_token_keys(pasted_text)
        if not parsed:
            return
        by_id = merge_pasted_keys(tokens, parsed)
        self._merge(by_id, {})
        for name, key in parsed.items():
            if not name.startswith("__sk_only__:"):
                self.by_name[name] = key
        if by_id or any(not k.startswith("__sk_only__:") for k in parsed):
            self.sources.append("pasted")

    def _merge(self, by_id: dict[int, str], by_name: dict[str, str]) -> None:
        self.by_id.update(by_id)
        self.by_name.update(by_name)

    def resolve(self, token: dict[str, Any]) -> str:
        api_key = str(token.get("key") or "").strip()
        if api_key and not is_masked_key(api_key):
            return api_key

        token_id = token.get("id")
        if token_id is not None:
            hit = self.by_id.get(int(token_id))
            if hit:
                return hit

        name = str(token.get("name") or "").strip()
        if name:
            hit = self.by_name.get(name)
            if hit:
                return hit

        return api_key

    def fetch_plain_keys(
        self,
        client: NewAPIClient,
        tokens: list[dict[str, Any]],
        *,
        batch_size: int = 100,
    ) -> int:
        """对脱敏令牌调用 key 专用 API，返回成功解析的数量。"""
        masked_ids: list[int] = []
        for token in tokens:
            token_id = token.get("id")
            if token_id is None:
                continue
            if is_masked_key(str(token.get("key") or "")):
                masked_ids.append(int(token_id))
            elif int(token_id) not in self.by_id:
                plain = str(token.get("key") or "").strip()
                if plain:
                    self.by_id[int(token_id)] = plain

        if not masked_ids:
            return 0

        fetched = 0
        for start in range(0, len(masked_ids), batch_size):
            chunk = masked_ids[start : start + batch_size]
            keys_map: dict[int, str] = {}
            try:
                keys_map = client.fetch_token_keys_batch(chunk)
            except Exception:  # noqa: BLE001
                keys_map = {}

            missing = [token_id for token_id in chunk if token_id not in keys_map]
            for token_id in missing:
                try:
                    keys_map[token_id] = client.fetch_token_key(token_id)
                except Exception:  # noqa: BLE001
                    continue

            for token_id, key in keys_map.items():
                text = str(key or "").strip()
                if not text or is_masked_key(text):
                    continue
                self.by_id[int(token_id)] = text
                fetched += 1

        if fetched and "key_api" not in self.sources:
            self.sources.append("key_api")
        return fetched

    def remember_created(self, token: dict[str, Any], key: str) -> None:
        save_token_key(
            self.base_url,
            token_id=int(token["id"]) if token.get("id") is not None else None,
            name=str(token.get("name") or "").strip() or None,
            key=key,
        )
        if token.get("id") is not None:
            self.by_id[int(token["id"])] = key.strip()
        name = str(token.get("name") or "").strip()
        if name:
            self.by_name[name] = key.strip()
