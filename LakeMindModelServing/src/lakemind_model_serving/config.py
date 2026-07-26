from __future__ import annotations

import os
import yaml
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 10824
    api_key: str = "lakemind-modelserving-key"


@dataclass
class GatewayConfig:
    default_chat_model: str = "auto"
    default_embed_model: str = "auto"
    fallback: dict = field(default_factory=dict)
    cache: bool = False


@dataclass
class EmbeddingBuiltInConfig:
    enabled: bool = True
    provider: str = "fastembed"
    model: str = "jinaai/jina-embeddings-v2-base-zh"
    dim: int = 768
    cache_dir: str = "/data/fastembed_cache"


@dataclass
class EmbeddingConfig:
    built_in: EmbeddingBuiltInConfig = field(default_factory=EmbeddingBuiltInConfig)
    external: list = field(default_factory=list)


@dataclass
class ASRBuiltInConfig:
    enabled: bool = True
    required: bool = False
    preload: bool = True
    provider: str = "sensevoice-funasr"
    model_alias: str = "sensevoice-small"
    model_id: str = "iic/SenseVoiceSmall"
    model_revision: str = ""
    model_path: str = "/models/asr/sensevoice-small"
    language: str = "zh"
    device: str = "cpu"
    compute_type: str = "int8"
    cpu_threads: int = 4
    num_workers: int = 1
    concurrency: int = 2
    beam_size: int = 1
    vad_filter: bool = False
    vad_min_silence_duration_ms: int = 500
    condition_on_previous_text: bool = False
    word_timestamps: bool = False
    intra_threads: int = 2
    inter_threads: int = 1
    use_itn: bool = True
    vad: bool = False
    max_upload_mb: int = 100
    request_timeout_seconds: int = 600


@dataclass
class ASRConfig:
    built_in: ASRBuiltInConfig = field(default_factory=ASRBuiltInConfig)
    external: list = field(default_factory=list)
    total_concurrency: int = 2


@dataclass
class RegistryConfig:
    host: str = "lakemind-postgres"
    port: int = 5432
    db: str = "lakemind"
    user: str = "lakemind"
    password: str = "lakemind_pass"


@dataclass
class ModelsConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    providers: list = field(default_factory=list)
    models: list = field(default_factory=list)
    llm_providers: list = field(default_factory=list)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    registry: RegistryConfig = field(default_factory=RegistryConfig)


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            return os.environ.get(var_name, "")
        return value
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load_config(path: str | None = None) -> ModelsConfig:
    if path is None:
        path = os.environ.get("LAKE_CONFIG", "/etc/lakemind/models.yaml")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    raw = _resolve_env(raw)

    server_raw = raw.get("server", {})
    server = ServerConfig(
        host=server_raw.get("host", "0.0.0.0"),
        port=server_raw.get("port", 10824),
        api_key=os.environ.get("MODELSERVING_API_KEY", server_raw.get("api_key", "lakemind-modelserving-key")),
    )

    gw_raw = raw.get("gateway", {})
    gateway = GatewayConfig(
        default_chat_model=gw_raw.get("default_chat_model", "auto"),
        default_embed_model=gw_raw.get("default_embed_model", "auto"),
        fallback=gw_raw.get("fallback", {}),
        cache=gw_raw.get("cache", False),
    )

    llm_providers = raw.get("llm_providers", [])
    providers = raw.get("providers", [])
    models_cfg = raw.get("models", [])

    emb_raw = raw.get("embedding", {})
    bi_raw = emb_raw.get("built_in", {})
    embedding = EmbeddingConfig(
        built_in=EmbeddingBuiltInConfig(
            enabled=bi_raw.get("enabled", True),
            provider=bi_raw.get("provider", "fastembed"),
            model=bi_raw.get("model", "jinaai/jina-embeddings-v2-base-zh"),
            dim=bi_raw.get("dim", 768),
            cache_dir=bi_raw.get("cache_dir", "/data/fastembed_cache"),
        ),
        external=emb_raw.get("external", []),
    )

    asr_raw = raw.get("asr", {})
    abi_raw = asr_raw.get("built_in", {})
    asr = ASRConfig(
        built_in=ASRBuiltInConfig(
            enabled=abi_raw.get("enabled", True),
            required=abi_raw.get("required", False),
            preload=abi_raw.get("preload", True),
            provider=abi_raw.get("provider", "sensevoice-funasr"),
            model_alias=abi_raw.get("model_alias", "sensevoice-small"),
            model_id=abi_raw.get("model_id", "iic/SenseVoiceSmall"),
            model_revision=abi_raw.get("model_revision", ""),
            model_path=abi_raw.get("model_path", "/models/asr/sensevoice-small"),
            language=abi_raw.get("language", "zh"),
            device=abi_raw.get("device", "cpu"),
            compute_type=abi_raw.get("compute_type", "int8"),
            cpu_threads=abi_raw.get("cpu_threads", 4),
            num_workers=abi_raw.get("num_workers", 1),
            concurrency=abi_raw.get("concurrency", 2),
            beam_size=abi_raw.get("beam_size", 1),
            vad_filter=abi_raw.get("vad_filter", False),
            vad_min_silence_duration_ms=abi_raw.get("vad_min_silence_duration_ms", 500),
            condition_on_previous_text=abi_raw.get("condition_on_previous_text", False),
            word_timestamps=abi_raw.get("word_timestamps", False),
            intra_threads=abi_raw.get("intra_threads", 2),
            inter_threads=abi_raw.get("inter_threads", 1),
            use_itn=abi_raw.get("use_itn", True),
            vad=abi_raw.get("vad", False),
            max_upload_mb=abi_raw.get("max_upload_mb", 100),
            request_timeout_seconds=abi_raw.get("request_timeout_seconds", 600),
        ),
        external=asr_raw.get("external", []),
        total_concurrency=asr_raw.get("total_concurrency", 2),
    )

    reg_raw = raw.get("registry", {})
    registry = RegistryConfig(
        host=reg_raw.get("host", "lakemind-postgres"),
        port=reg_raw.get("port", 5432),
        db=reg_raw.get("db", "lakemind"),
        user=reg_raw.get("user", "lakemind"),
        password=reg_raw.get("password", "lakemind_pass"),
    )

    return ModelsConfig(
        server=server,
        gateway=gateway,
        providers=providers,
        models=models_cfg,
        llm_providers=llm_providers,
        embedding=embedding,
        asr=asr,
        registry=registry,
    )
