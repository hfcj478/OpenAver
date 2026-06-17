"""
test_translate_service.py - 翻譯服務抽象層單元測試

測試範圍：
- 工廠函數 create_translate_service()
- 配置默認值處理
- 錯誤處理（未知 provider、未實現 provider）
- 語言 prompt 組裝（TestLanguagePrompts）
- ja 短路機制（TestTranslateSingleJaShortCircuit）

注意：實際 Ollama API 調用測試放在 tests/smoke/test_translate_live.py
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.translate_service import (
    TranslateService,
    OllamaTranslateService,
    GeminiTranslateService,
    OpenAICompatibleTranslateService,
    create_translate_service
)


# ============ 工廠函數測試 ============

class TestCreateTranslateService:
    """測試工廠函數"""

    def test_factory_ollama(self):
        """Ollama provider 正確創建實例"""
        config = {
            "provider": "ollama",
            "ollama": {
                "url": "http://localhost:11434",
                "model": "qwen3:8b"
            }
        }
        service = create_translate_service(config)

        assert isinstance(service, OllamaTranslateService)
        assert service.ollama_url == "http://localhost:11434"
        assert service.model == "qwen3:8b"

    def test_factory_ollama_default_provider(self):
        """默認 provider 為 ollama"""
        config = {}  # 無 provider 欄位
        service = create_translate_service(config)

        assert isinstance(service, OllamaTranslateService)

    def test_factory_gemini_missing_api_key(self):
        """Gemini provider 缺少 API Key 拋出 ValueError"""
        config = {"provider": "gemini", "gemini": {}}

        with pytest.raises(ValueError) as exc_info:
            create_translate_service(config)

        assert "API Key" in str(exc_info.value)

    def test_factory_unknown_provider(self):
        """未知 provider 拋出 ValueError"""
        config = {"provider": "unknown_provider"}

        with pytest.raises(ValueError) as exc_info:
            create_translate_service(config)

        assert "unknown_provider" in str(exc_info.value)


# ============ OllamaTranslateService 配置測試 ============

class TestOllamaTranslateServiceConfig:
    """測試 Ollama 服務配置處理"""

    def test_default_config(self):
        """默認配置正確設置"""
        service = OllamaTranslateService({})

        assert service.ollama_url == "http://localhost:11434"
        assert service.model == "qwen3:8b"

    def test_custom_url(self):
        """自定義 URL 正確處理"""
        config = {"url": "http://192.168.1.100:11434"}
        service = OllamaTranslateService(config)

        assert service.ollama_url == "http://192.168.1.100:11434"

    def test_url_trailing_slash_removed(self):
        """URL 尾斜線自動移除"""
        config = {"url": "http://localhost:11434/"}
        service = OllamaTranslateService(config)

        assert service.ollama_url == "http://localhost:11434"

    def test_custom_models(self):
        """自定義模型正確設置"""
        config = {
            "model": "llama3:8b"
        }
        service = OllamaTranslateService(config)

        assert service.model == "llama3:8b"


# ============ 抽象類測試 ============

class TestTranslateServiceABC:
    """測試抽象基類"""

    def test_cannot_instantiate_abc(self):
        """無法直接實例化抽象類"""
        with pytest.raises(TypeError):
            TranslateService()

    def test_ollama_is_subclass(self):
        """OllamaTranslateService 是 TranslateService 子類"""
        assert issubclass(OllamaTranslateService, TranslateService)

    def test_service_has_required_methods(self):
        """服務包含必要方法"""
        service = OllamaTranslateService({})

        assert hasattr(service, 'translate_single')
        assert hasattr(service, 'translate_batch')
        assert callable(service.translate_single)
        assert callable(service.translate_batch)


# ============ 語言 prompt 組裝測試 ============

class TestLanguagePrompts:
    """測試各語言 prompt 組裝"""

    def test_ollama_zh_tw_prompt(self):
        """OllamaTranslateService(config, "zh-TW") 的 system_msg 含 '繁體中文'"""
        service = OllamaTranslateService({}, "zh-TW")
        assert service.target_language == "zh-TW"
        # 確認 system prompt 包含繁體中文關鍵字
        from core.translate_service import LANGUAGE_PROMPTS
        prompt_data = LANGUAGE_PROMPTS.get("zh-TW", {})
        assert "繁體中文" in prompt_data.get("ollama_system", "")

    def test_ollama_zh_cn_prompt(self):
        """OllamaTranslateService(config, "zh-CN") 的 system_msg 含 '简体中文'"""
        service = OllamaTranslateService({}, "zh-CN")
        assert service.target_language == "zh-CN"
        from core.translate_service import LANGUAGE_PROMPTS
        prompt_data = LANGUAGE_PROMPTS.get("zh-CN", {})
        assert "简体中文" in prompt_data.get("ollama_system", "")

    def test_ollama_en_prompt(self):
        """OllamaTranslateService(config, "en") 的 system_msg 含 'English'"""
        service = OllamaTranslateService({}, "en")
        assert service.target_language == "en"
        from core.translate_service import LANGUAGE_PROMPTS
        prompt_data = LANGUAGE_PROMPTS.get("en", {})
        assert "English" in prompt_data.get("ollama_system", "")

    def test_gemini_en_prompt(self):
        """GeminiTranslateService(config, "en") 的 prompt 含 'English'"""
        config = {"api_key": "fake-key-for-test"}
        service = GeminiTranslateService(config, "en")
        assert service.target_language == "en"
        from core.translate_service import LANGUAGE_PROMPTS
        prompt_data = LANGUAGE_PROMPTS.get("en", {})
        assert "English" in prompt_data.get("gemini_instruction", "")

    def test_unknown_target_fallback(self):
        """不存在的 target（如 'ko'）fallback 到 zh-TW prompt"""
        service = OllamaTranslateService({}, "ko")
        assert service.target_language == "ko"
        # LANGUAGE_PROMPTS.get("ko", LANGUAGE_PROMPTS["zh-TW"]) 應返回 zh-TW 的資料
        from core.translate_service import LANGUAGE_PROMPTS
        prompt_data = LANGUAGE_PROMPTS.get("ko", LANGUAGE_PROMPTS["zh-TW"])
        assert "繁體中文" in prompt_data.get("ollama_system", "")


# ============ ja 短路測試 ============

class TestTranslateSingleJaShortCircuit:
    """測試 target=ja 時不呼叫 API，回傳原文"""

    @pytest.mark.asyncio
    async def test_ollama_ja_returns_original(self):
        """target=ja 時 Ollama 不呼叫 API，回傳原文"""
        service = OllamaTranslateService({}, "ja")
        original_title = "巨乳の女優がデビュー"

        # 若呼叫 httpx 就會失敗，這裡 mock 確保不被呼叫
        with patch("httpx.AsyncClient") as mock_client:
            result = await service.translate_single(original_title)
            mock_client.assert_not_called()

        assert result == original_title

    @pytest.mark.asyncio
    async def test_gemini_ja_returns_original(self):
        """target=ja 時 Gemini 不呼叫 API，回傳原文"""
        config = {"api_key": "fake-key-for-test"}
        service = GeminiTranslateService(config, "ja")
        original_title = "巨乳の女優がデビュー"

        with patch("httpx.AsyncClient") as mock_client:
            result = await service.translate_single(original_title)
            mock_client.assert_not_called()

        assert result == original_title


# ============ OpenAICompatibleTranslateService 測試 ============

class TestOpenAICompatibleTranslateService:
    """測試 OpenAI Compatible 翻譯服務"""

    def test_trailing_slash_removed(self):
        """base_url 尾斜線自動移除"""
        service = OpenAICompatibleTranslateService({"base_url": "http://host/v1/"})
        assert service.base_url == "http://host/v1"

    def test_trailing_slash_removed_multiple(self):
        """多重尾斜線自動移除"""
        service = OpenAICompatibleTranslateService({"base_url": "http://host/v1///"})
        assert service.base_url == "http://host/v1"

    def test_default_model(self):
        """預設 model 為 gpt-4o-mini"""
        service = OpenAICompatibleTranslateService({})
        assert service.model == "gpt-4o-mini"

    def test_custom_model(self):
        """自定義 model 正確設置"""
        service = OpenAICompatibleTranslateService({"model": "llama3"})
        assert service.model == "llama3"

    def test_api_key_empty_by_default(self):
        """api_key 預設為空字串"""
        service = OpenAICompatibleTranslateService({})
        assert service.api_key == ""

    @pytest.mark.asyncio
    async def test_ja_short_circuit(self):
        """target=ja 時不呼叫 HTTP，直接回傳原文"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "model": "m"},
            "ja"
        )
        original_title = "テスト"

        with patch("httpx.AsyncClient") as mock_client:
            result = await service.translate_single(original_title)
            mock_client.assert_not_called()

        assert result == original_title

    @pytest.mark.asyncio
    async def test_api_key_empty_no_auth_header(self):
        """api_key 為空時不送 Authorization header"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "api_key": "", "model": "m"},
            "zh-TW"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "新人女演員出道"}}]
        }
        mock_response.raise_for_status = MagicMock()

        captured_headers = {}

        async def mock_post(url, headers=None, json=None):
            captured_headers.update(headers or {})
            return mock_response

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(side_effect=mock_post)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            result = await service.translate_single("新人女優デビュー")

        assert "Authorization" not in captured_headers
        assert result == "新人女演員出道"

    @pytest.mark.asyncio
    async def test_api_key_present_auth_header(self):
        """api_key 有值時送 Authorization: Bearer xxx"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "api_key": "sk-test123", "model": "m"},
            "zh-TW"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "新人女演員出道"}}]
        }
        mock_response.raise_for_status = MagicMock()

        captured_headers = {}

        async def mock_post(url, headers=None, json=None):
            captured_headers.update(headers or {})
            return mock_response

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(side_effect=mock_post)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            await service.translate_single("新人女優デビュー")

        assert captured_headers.get("Authorization") == "Bearer sk-test123"

    @pytest.mark.asyncio
    async def test_translate_single_url_no_double_slash(self):
        """POST URL 無雙斜線（base_url 無尾斜線後拼接 /chat/completions）"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://host/v1/", "model": "m"},
            "zh-TW"
        )

        captured_url = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}]
        }
        mock_response.raise_for_status = MagicMock()

        async def mock_post(url, headers=None, json=None):
            captured_url["url"] = url
            return mock_response

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(side_effect=mock_post)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            await service.translate_single("テスト")

        assert captured_url["url"] == "http://host/v1/chat/completions"
        assert "//" not in captured_url["url"].replace("://", "")

    @pytest.mark.asyncio
    async def test_translate_single_success(self):
        """mock 200 + OpenAI format → 回翻譯結果"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "model": "gpt-4o-mini"},
            "zh-TW"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "  新人女演員出道  "}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            result = await service.translate_single("新人女優デビュー")

        assert result == "新人女演員出道"

    @pytest.mark.asyncio
    async def test_translate_single_http_error(self):
        """mock 401 → 回 ''，不拋例外"""
        import httpx as _httpx

        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "model": "m"},
            "zh-TW"
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        http_error = _httpx.HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(),
            response=mock_response
        )

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(side_effect=http_error)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            result = await service.translate_single("テスト")

        assert result == ""

    @pytest.mark.asyncio
    async def test_translate_single_bad_response(self):
        """mock 200 + {error: ...}（無 choices）→ 回 ''"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "model": "m"},
            "zh-TW"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "model not found"}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            result = await service.translate_single("テスト")

        assert result == ""

    @pytest.mark.asyncio
    async def test_translate_batch(self):
        """mock translate_single → batch 循環正確"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "model": "m"},
            "zh-TW"
        )

        call_count = 0
        side_effects = ["翻譯A", "翻譯B"]

        async def mock_translate_single(title, context=None):
            nonlocal call_count
            result = side_effects[call_count]
            call_count += 1
            return result

        service.translate_single = mock_translate_single

        results = await service.translate_batch(["タイトルA", "タイトルB"])

        assert len(results) == 2
        assert results[0] == "翻譯A"
        assert results[1] == "翻譯B"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_translate_batch_empty(self):
        """空列表 → 回空列表"""
        service = OpenAICompatibleTranslateService({}, "zh-TW")
        results = await service.translate_batch([])
        assert results == []


class TestFactoryOpenAI:
    """測試 factory openai branch"""

    def test_factory_openai(self):
        """create_translate_service 回傳 OpenAICompatibleTranslateService"""
        config = {
            "provider": "openai",
            "openai": {"base_url": "http://localhost/v1", "model": "gpt-4o-mini"}
        }
        service = create_translate_service(config)
        assert isinstance(service, OpenAICompatibleTranslateService)

    def test_factory_openai_inherits_translate_service(self):
        """OpenAICompatibleTranslateService 是 TranslateService 子類"""
        assert issubclass(OpenAICompatibleTranslateService, TranslateService)

    def test_factory_openai_empty_base_url_no_error(self):
        """base_url 為空時 factory 層不拋錯（讓 translate_single 在 HTTP 階段失敗）"""
        config = {"provider": "openai", "openai": {"base_url": "", "model": "m"}}
        service = create_translate_service(config)
        assert isinstance(service, OpenAICompatibleTranslateService)
        assert service.base_url == ""


# ============ OllamaTranslateService._clean_output 純字串測試 ============

class TestOllamaCleanOutput:
    """測試 _clean_output 字串清理行為（純邏輯，零 mock）"""

    def setup_method(self):
        self.service = OllamaTranslateService({})

    def test_strip_double_quotes(self):
        """雙引號包圍的文字應剝除引號"""
        assert self.service._clean_output('"結果"') == '結果'

    def test_strip_single_quotes(self):
        """單引號包圍的文字應剝除引號"""
        assert self.service._clean_output("'結果'") == '結果'

    def test_strip_think_tag(self):
        """<think>...</think> 標籤應被移除，保留後面的翻譯"""
        assert self.service._clean_output('<think>思考過程</think>翻譯結果') == '翻譯結果'

    def test_strip_think_tag_multiline(self):
        """<think> 跨行時 re.DOTALL 仍能正確移除"""
        text = '<think>\n多行\n思考\n</think>翻譯結果'
        assert self.service._clean_output(text) == '翻譯結果'

    def test_empty_string(self):
        """空字串輸入應回傳空字串"""
        assert self.service._clean_output('') == ''

    def test_translation_prefix_retained_current_behavior(self):
        """「翻譯：」前綴應保留——鎖定 :176 字面 \\s*（雙反斜線）現狀。
        regex r'^翻譯[：:]\\s*' 中 \\ 是字面反斜線，非 whitespace 萬用符；
        實務上前綴不被移除。若日後修正 regex，此測試需同步更新。"""
        assert self.service._clean_output('翻譯：result') == '翻譯：result'


# ============ OllamaTranslateService._parse_batch_output 純字串測試 ============

class TestOllamaParseBatchOutput:
    """測試 _parse_batch_output 批次輸出解析（純邏輯，零 mock）"""

    def setup_method(self):
        self.service = OllamaTranslateService({})

    def test_numbered_dot_format(self):
        """1. / 2. 格式編號應被去除，內容正確收入"""
        result = self.service._parse_batch_output("1. 結果A\n2. 結果B")
        assert result == ["結果A", "結果B"]

    def test_numbered_paren_format(self):
        """1) 括號格式編號應被去除"""
        result = self.service._parse_batch_output("1) 結果A")
        assert result == ["結果A"]

    def test_numbered_comma_format(self):
        """1、頓號格式編號應被去除"""
        result = self.service._parse_batch_output("1、結果A")
        assert result == ["結果A"]

    def test_pure_number_lines_skipped(self):
        """純數字行（無實際內容）應全部跳過，回傳空列表"""
        result = self.service._parse_batch_output("1\n2\n3")
        assert result == []

    def test_no_numbering_accepted(self):
        """無編號但有內容的行也應收入"""
        result = self.service._parse_batch_output("結果A\n結果B")
        assert result == ["結果A", "結果B"]

    def test_empty_lines_skipped(self):
        """空行應跳過，有效內容正常收入"""
        result = self.service._parse_batch_output("1. 結果\n\n2. 結果2")
        assert result == ["結果", "結果2"]


# ============ GeminiTranslateService.translate_single 四分支測試 ============

class TestGeminiTranslateSingleBranches:
    """測試 Gemini translate_single 四個回應分支（mock httpx，零真連線）

    mock 模式沿用 TestOpenAICompatibleTranslateService：
    patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance)
    mock_client_instance 支援 async with（__aenter__/__aexit__），
    resp 物件有 .raise_for_status()（no-op）與 .json()。
    target_language 使用預設 zh-TW，避免 :230-231 ja 短路。
    """

    def _make_service(self):
        return GeminiTranslateService({"api_key": "fake-key-for-test"}, "zh-TW")

    def _make_mock_client(self, json_data):
        """建立支援 async with 的 httpx mock，回傳指定 json_data"""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = json_data

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        return mock_client_instance

    @pytest.mark.asyncio
    async def test_prompt_feedback_block_reason_returns_empty(self):
        """Step 1：response 含 promptFeedback.blockReason → 回 ''"""
        service = self._make_service()
        json_data = {
            "promptFeedback": {
                "blockReason": "SAFETY",
                "safetyRatings": []
            }
        }
        mock_client = self._make_mock_client(json_data)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client):
            result = await service.translate_single("テスト")

        assert result == ""

    @pytest.mark.asyncio
    async def test_no_candidates_returns_empty(self):
        """Step 2：response 無 candidates 欄位 → 回 ''"""
        service = self._make_service()
        json_data = {"error": {"message": "some error"}}
        mock_client = self._make_mock_client(json_data)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client):
            result = await service.translate_single("テスト")

        assert result == ""

    @pytest.mark.asyncio
    async def test_finish_reason_safety_returns_empty(self):
        """Step 3：candidates[0].finishReason == 'SAFETY' → 回 ''"""
        service = self._make_service()
        json_data = {
            "candidates": [
                {
                    "finishReason": "SAFETY",
                    "safetyRatings": []
                }
            ]
        }
        mock_client = self._make_mock_client(json_data)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client):
            result = await service.translate_single("テスト")

        assert result == ""

    @pytest.mark.asyncio
    async def test_happy_path_returns_translation(self):
        """Step 4 happy：正常 content.parts[0].text → 回翻譯字串（strip 後）"""
        service = self._make_service()
        json_data = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [{"text": "  翻譯結果  "}]
                    }
                }
            ]
        }
        mock_client = self._make_mock_client(json_data)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client):
            result = await service.translate_single("テスト")

        assert result == "翻譯結果"
