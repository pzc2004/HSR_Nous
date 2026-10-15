"""tribios 运行器接线测试（mock 传输层，不接真 API）——配置/热更/消息形状/ping."""

from __future__ import annotations

import json

from hsr_nous.ops.annotator.llm import make_tribios_runner, ping

_ENV = {
    "HSR_NOUS_LLM_ANNOTATOR_API_KEY": "test-key-1,test-key-2",
    "HSR_NOUS_LLM_ANNOTATOR_MODEL": "test-model",
    "HSR_NOUS_LLM_ANNOTATOR_API_BASE": "https://api.test/v1",
}


def _mock_transport(captured: list):
    def transport(url, payload, headers):
        captured.append({"url": url, "payload": payload, "headers": headers})

        class Resp:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": "正常"}}]}
        return Resp()
    return transport


def test_runner_chat_shape(tmp_path):
    captured = []
    runner = make_tribios_runner(live_path=tmp_path / "live.json",
                                 transport=_mock_transport(captured), env=dict(_ENV))
    out = runner(system="你是证据研究员", prompt="写证据笔记", max_tokens=123)
    assert out == "正常"
    assert len(captured) == 1
    call = captured[0]
    assert call["url"] == "https://api.test/v1/chat/completions"
    assert call["payload"]["model"] == "test-model"
    assert call["payload"]["max_tokens"] == 123
    assert [m["role"] for m in call["payload"]["messages"]] == ["system", "user"]
    assert call["headers"]["Authorization"].startswith("Bearer test-key-")


def test_live_config_hot_reload(tmp_path):
    captured = []
    live_file = tmp_path / "live.json"
    runner = make_tribios_runner(live_path=live_file,
                                 transport=_mock_transport(captured), env=dict(_ENV))
    runner(system="s", prompt="p")
    live_file.write_text(json.dumps({"model": "new-model", "api_base": "https://api.new/v2"}),
                         encoding="utf-8")
    runner(system="s", prompt="p")
    assert captured[1]["url"] == "https://api.new/v2/chat/completions", "热更生效于之后派发"
    assert captured[1]["payload"]["model"] == "new-model"


def test_ping_ok(tmp_path):
    out = ping(live_path=tmp_path / "live.json", transport=_mock_transport([]), env=dict(_ENV))
    assert "ping OK" in out and "test-model" in out and "keys=2" in out
    assert "test-key" not in out.replace("keys=", ""), "ping 输出永不回显 key"
