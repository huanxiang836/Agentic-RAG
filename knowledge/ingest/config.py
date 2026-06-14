"""集中管理 Markdown 入库链路配置。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    """Markdown 入库链路运行配置。"""

    chatModel: str
    embeddingModel: str
    embeddingApiKey: str
    openaiBaseUrl: str
    milvusHost: str
    milvusPort: int
    milvusUsername: str
    milvusPassword: str
    milvusDatabase: str
    milvusCollection: str
    milvusEmbeddingDimension: int
    projectRoot: Path
    dataDir: Path
    embeddingTimeoutSeconds: float = 30.0
    embeddingMaxRetries: int = 3
    milvusInsertBatchSize: int = 64

    @classmethod
    def fromEnv(cls) -> "AppConfig":
        """从环境变量构造配置，并尽早暴露缺失项。"""

        load_dotenv()
        # knowledge/ingest/config.py 位于项目根目录下两层，固定回溯两级可稳定定位项目根目录。
        projectRoot = Path(__file__).resolve().parents[2]
        dataDir = projectRoot / "data"
        config = cls(
            chatModel=_requireEnv("CHAT_MODEL"),
            embeddingModel=_requireEnv("EMBEDDING_MODEL"),
            embeddingApiKey=_requireEnv("EMBEDDING_API_KEY"),
            openaiBaseUrl=_normalizeOpenaiBaseUrl(_requireEnv("OPENAI_BASE_URL")),
            milvusHost=_requireEnv("MILVUS_HOST"),
            milvusPort=_requireIntEnv("MILVUS_PORT"),
            milvusUsername=_requireEnv("MILVUS_USERNAME"),
            milvusPassword=_requireEnv("MILVUS_PASSWORD"),
            milvusDatabase=_requireEnv("MILVUS_DATABASE"),
            milvusCollection=_requireEnv("MILVUS_COLLECTION"),
            milvusEmbeddingDimension=_requireIntEnv("MILVUS_EMBEDDING_DIMENSION"),
            projectRoot=projectRoot,
            dataDir=dataDir,
        )
        config.validate()
        return config

    def validate(self) -> None:
        """校验关键配置，避免把错误拖到外部依赖初始化阶段。"""

        if self.embeddingModel != "BAAI/bge-m3":
            raise ValueError("EMBEDDING_MODEL 必须为 BAAI/bge-m3。")
        if self.chatModel != "qwen3.6-plus":
            raise ValueError("CHAT_MODEL 必须为 qwen3.6-plus。")
        if not self.dataDir.exists():
            raise ValueError(f"数据目录不存在: {self.dataDir}")
        if self.milvusPort <= 0:
            raise ValueError("MILVUS_PORT 必须是正整数。")
        if self.milvusEmbeddingDimension <= 0:
            raise ValueError("MILVUS_EMBEDDING_DIMENSION 必须是正整数。")

    @property
    def milvusUri(self) -> str:
        """统一生成 Milvus 连接地址，避免不同模块拼接不一致。"""

        return f"http://{self.milvusHost}:{self.milvusPort}"


def _requireEnv(name: str) -> str:
    """强制读取非空环境变量。"""

    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"缺少必需环境变量: {name}")
    return value


def _requireIntEnv(name: str) -> int:
    """读取整数环境变量，并给出清晰错误。"""

    rawValue = _requireEnv(name)
    try:
        return int(rawValue)
    except ValueError as error:
        raise ValueError(f"环境变量 {name} 必须为整数，当前值: {rawValue}") from error


def _normalizeOpenaiBaseUrl(baseUrl: str) -> str:
    """兼容 OpenAI 风格服务端，统一补齐 `/v1` 路径。"""

    normalizedUrl = baseUrl.rstrip("/")
    if normalizedUrl.endswith("/v1"):
        return normalizedUrl
    return f"{normalizedUrl}/v1"
