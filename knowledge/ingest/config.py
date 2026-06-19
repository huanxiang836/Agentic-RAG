"""集中管理 Markdown 入库链路配置。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    """Markdown 入库与 RAG 运行配置。"""

    chatModel: str
    judgeModel: str
    embeddingModel: str
    siliconflowApiKey: str
    siliconflowBaseUrl: str
    rerankModel: str
    milvusHost: str
    milvusPort: int
    milvusUsername: str
    milvusPassword: str
    milvusDatabase: str
    milvusCollection: str
    milvusEmbeddingDimension: int
    onlineChatRetrievalEnhancedEnabled: bool
    queryRewriteEnabled: bool
    rerankEnabled: bool
    projectRoot: Path
    dataDir: Path
    embeddingTimeoutSeconds: float = 30.0
    embeddingMaxRetries: int = 3
    milvusTimeoutSeconds: float = 180.0
    milvusInsertBatchSize: int = 64
    chatModelTimeoutSeconds: float = 180.0
    judgeModelTimeoutSeconds: float = 180.0
    queryRewriteTimeoutSeconds: float = 30.0
    rerankTimeoutSeconds: float = 30.0
    ragasEvaluationTimeoutSeconds: float = 600.0

    @classmethod
    def fromEnv(cls) -> "AppConfig":
        """从环境变量构造配置，并尽早暴露缺失项。"""

        load_dotenv()
        # knowledge/ingest/config.py 位于项目根目录下两层，固定回溯两级可稳定定位项目根目录。
        projectRoot = Path(__file__).resolve().parents[2]
        dataDir = projectRoot / "data"
        config = cls(
            chatModel=_requireEnv("CHAT_MODEL"),
            judgeModel=_requireEnv("JUDGE_MODEL"),
            embeddingModel=_requireEnv("EMBEDDING_MODEL"),
            siliconflowApiKey=_requireEnv("SILICONFLOW_API_KEY"),
            siliconflowBaseUrl=_normalizeSiliconflowBaseUrl(_requireEnv("SILICONFLOW_BASE_URL")),
            rerankModel=_requireEnv("RERANK_MODEL"),
            milvusHost=_requireEnv("MILVUS_HOST"),
            milvusPort=_requireIntEnv("MILVUS_PORT"),
            milvusUsername=_requireEnv("MILVUS_USERNAME"),
            milvusPassword=_requireEnv("MILVUS_PASSWORD"),
            milvusDatabase=_requireEnv("MILVUS_DATABASE"),
            milvusCollection=_requireEnv("MILVUS_COLLECTION"),
            milvusEmbeddingDimension=_requireIntEnv("MILVUS_EMBEDDING_DIMENSION"),
            onlineChatRetrievalEnhancedEnabled=_requireBoolEnv(
                "RAG_ONLINE_CHAT_RETRIEVAL_ENHANCED_ENABLED",
                True,
            ),
            queryRewriteEnabled=_requireBoolEnv("RAG_QUERY_REWRITE_ENABLED", True),
            rerankEnabled=_requireBoolEnv("RAG_RERANK_ENABLED", True),
            projectRoot=projectRoot,
            dataDir=dataDir,
            chatModelTimeoutSeconds=_requireFloatEnv("CHAT_MODEL_TIMEOUT_SECONDS", 180.0),
            judgeModelTimeoutSeconds=_requireFloatEnv("JUDGE_MODEL_TIMEOUT_SECONDS", 180.0),
            queryRewriteTimeoutSeconds=_requireFloatEnv(
                "RAG_QUERY_REWRITE_TIMEOUT_SECONDS",
                30.0,
            ),
            rerankTimeoutSeconds=_requireFloatEnv("RAG_RERANK_TIMEOUT_SECONDS", 30.0),
            ragasEvaluationTimeoutSeconds=_requireFloatEnv(
                "RAGAS_EVALUATION_TIMEOUT_SECONDS",
                600.0,
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:  # pylint: disable=too-many-branches
        """校验关键配置，避免把错误拖到外部依赖初始化阶段。"""

        if self.embeddingModel != "BAAI/bge-m3":
            raise ValueError("EMBEDDING_MODEL 必须为 BAAI/bge-m3。")
        if not self.siliconflowApiKey:
            raise ValueError("SILICONFLOW_API_KEY 不能为空。")
        if not self.siliconflowBaseUrl:
            raise ValueError("SILICONFLOW_BASE_URL 不能为空。")
        if not self.rerankModel:
            raise ValueError("RERANK_MODEL 不能为空。")
        if not self.chatModel:
            raise ValueError("CHAT_MODEL 不能为空。")
        if not self.judgeModel:
            raise ValueError("JUDGE_MODEL 不能为空。")
        if not self.dataDir.exists():
            raise ValueError(f"数据目录不存在: {self.dataDir}")
        if self.milvusPort <= 0:
            raise ValueError("MILVUS_PORT 必须是正整数。")
        if self.milvusEmbeddingDimension <= 0:
            raise ValueError("MILVUS_EMBEDDING_DIMENSION 必须是正整数。")
        if not isinstance(self.onlineChatRetrievalEnhancedEnabled, bool):
            raise ValueError("RAG_ONLINE_CHAT_RETRIEVAL_ENHANCED_ENABLED 必须是布尔值。")
        if self.chatModelTimeoutSeconds <= 0:
            raise ValueError("CHAT_MODEL_TIMEOUT_SECONDS 必须是正数。")
        if self.judgeModelTimeoutSeconds <= 0:
            raise ValueError("JUDGE_MODEL_TIMEOUT_SECONDS 必须是正数。")
        if self.queryRewriteTimeoutSeconds <= 0:
            raise ValueError("RAG_QUERY_REWRITE_TIMEOUT_SECONDS 必须是正数。")
        if self.rerankTimeoutSeconds <= 0:
            raise ValueError("RAG_RERANK_TIMEOUT_SECONDS 必须是正数。")
        if self.ragasEvaluationTimeoutSeconds <= 0:
            raise ValueError("RAGAS_EVALUATION_TIMEOUT_SECONDS 必须是正数。")

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


def _requireFloatEnv(name: str, default: float) -> float:
    """读取浮点环境变量，缺省时使用默认值。"""

    rawValue = os.getenv(name, "").strip()
    if not rawValue:
        return default
    try:
        return float(rawValue)
    except ValueError as error:
        raise ValueError(f"环境变量 {name} 必须为数字，当前值: {rawValue}") from error


def _requireBoolEnv(name: str, default: bool) -> bool:
    """读取布尔环境变量，缺省时使用默认值。"""

    rawValue = os.getenv(name, "").strip()
    if not rawValue:
        return default
    normalizedValue = rawValue.lower()
    if normalizedValue in {"1", "true", "yes", "on"}:
        return True
    if normalizedValue in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"环境变量 {name} 必须为布尔值，支持 true/false、1/0、yes/no、on/off，当前值: {rawValue}"
    )


def _normalizeSiliconflowBaseUrl(baseUrl: str) -> str:
    """兼容 OpenAI 风格服务端，统一补齐 `/v1` 路径。"""

    normalizedUrl = baseUrl.rstrip("/")
    if normalizedUrl.endswith("/v1"):
        return normalizedUrl
    return f"{normalizedUrl}/v1"
