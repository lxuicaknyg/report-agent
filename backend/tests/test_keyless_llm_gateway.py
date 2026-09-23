"""内网网关常常不设鉴权，构造 LLM 客户端不能因此失败。

这条曾经把整个部署打穿：连接服务会提前用这个客户端构造 SQL 工具，所以
LLM_API_KEY 留空时，/connections 和 /conversations 全部 500 —— 而那两个
接口本身并不需要模型。
"""

import pytest

from app.infrastructure.llm import OpenAICompatibleLlmService


def build(**kwargs):
    defaults = dict(base_url="http://gateway.intranet:8000/v1", api_key="", model="glm-5.3")
    return OpenAICompatibleLlmService(**{**defaults, **kwargs})


def test_empty_api_key_is_accepted():
    service = build()
    # SDK 不接受空 key，所以落到占位值上，而不是把异常抛给调用方。
    assert service.client.api_key == "EMPTY"


def test_a_real_key_is_passed_through():
    assert build(api_key="sk-real").client.api_key == "sk-real"


def test_base_url_and_model_are_still_required():
    # 这两个留空是配置漏了，没有合理的兜底值，必须明确报错。
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        build(base_url="")
    with pytest.raises(ValueError, match="LLM_MODEL_NAME"):
        build(model="")


def test_gateway_auth_failure_points_at_the_config_not_the_model():
    """厂商原文读起来像模型坏了，会把人引去查模型和额度。

    实际是 .env 里 LLM_API_KEY 没填，而且重试毫无意义 —— 凭据不会自己变对。
    """
    from app.conversations.orchestrator import ConversationOrchestrator

    orchestrator = ConversationOrchestrator.__new__(ConversationOrchestrator)
    raw = Exception(
        "Error code: 401 - {'error_msg': 'Api key auth failed, api key is "
        "invalid or empty', 'error_code': 'ModelArts.8902'}"
    )
    text = orchestrator._error_text(raw)
    assert "LLM_API_KEY" in text
    assert "ModelArts" not in text
