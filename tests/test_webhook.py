import pytest
from unittest.mock import patch, MagicMock
from app import app
from services.webhook_service import handle_webhook
from requests.models import Response

@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def app_context():
    with app.app_context():
        yield

def make_mock_linebindinguser(bound=True):
    mock_obj = MagicMock()
    mock_obj.first.return_value = object() if bound else None
    return mock_obj

# 測試 webhook endpoint 正常處理
@patch("services.webhook_service.requests.post")
@patch("services.webhook_service.line_bot_api.reply_message")
def test_webhook_post_valid(mock_reply_message, mock_requests_post, client):
    # 模擬 line_bot_api.reply_message 成功
    mock_reply_message.return_value = None

    # 模擬 requests.post 回傳成功結果
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_requests_post.return_value = mock_response

    data = {
        "events": [
            {
                "type": "message",
                "replyToken": "token123",
                "source": {"userId": "U123"},
                "message": {"text": "hello"}
            }
        ]
    }

    resp = client.post("/webhook", json=data)
    assert resp.status_code == 200

# 測試 webhook endpoint 收到錯誤資料
def test_webhook_post_invalid_json(client):
    resp = client.post("/webhook", data="notjson", content_type="application/json")
    # 你的程式可能回 400 或 500 依實作而定
    assert resp.status_code in (400, 500)

# 測試 handle_webhook: follow 事件且未綁定，應呼叫 send_bind_button
@patch("services.webhook_service.send_already_bound_msg")
@patch("services.webhook_service.send_bind_button")
@patch("services.webhook_service.LineBindingUser.query")
def test_handle_webhook_follow_unbound(mock_query, mock_bind_button, mock_already_bound_msg):
    # 模擬DB回傳綁定清單，不含這次 userId
    mock_query.with_entities.return_value.all.return_value = [MagicMock(line_id="U999")]
    event = {
        "events": [
            {
                "type": "follow",
                "replyToken": "rtoken",
                "source": {"userId": "U123"}
            }
        ]
    }
    result = handle_webhook(event, "token")
    mock_bind_button.assert_called_once_with("rtoken", "U123")
    mock_already_bound_msg.assert_not_called()
    assert result["status"] == "follow handled"

# 測試 handle_webhook: follow 事件且已綁定，應呼叫 send_already_bound_msg
@patch("services.webhook_service.LineBindingUser.query")
@patch("services.webhook_service.send_bind_button")
@patch("services.webhook_service.send_already_bound_msg")
def test_handle_webhook_follow_bound(mock_already_bound_msg, mock_bind_button, mock_query):
    mock_query.with_entities.return_value.all.return_value = [MagicMock(line_id="U123")]
    event = {
        "events": [
            {
                "type": "follow",
                "replyToken": "rtoken",
                "source": {"userId": "U123"}
            }
        ]
    }
    result = handle_webhook(event, "token")
    mock_bind_button.assert_not_called()
    mock_already_bound_msg.assert_called_once_with("rtoken")
    assert result["status"] == "follow handled"

# 測試 handle_webhook: message 事件，文字是"綁定"，且未綁定，應呼叫 send_bind_url
@patch("services.webhook_service.LineBindingUser.query.filter_by")
@patch("services.webhook_service.send_bind_url")
@patch("services.webhook_service.send_already_bound_msg")
def test_handle_webhook_message_bind_unbound(mock_already_bound_msg, mock_bind_url, mock_filter_by):
    mock_filter_by.return_value.first.return_value = None
    event = {
        "events": [
            {
                "type": "message",
                "replyToken": "rtoken",
                "source": {"userId": "U123"},
                "message": {"text": "綁定"}
            }
        ]
    }
    result = handle_webhook(event, "token")
    mock_bind_url.assert_called_once_with("rtoken", "U123")
    mock_already_bound_msg.assert_not_called()
    assert result["status"] == "binding handled"

# 測試 handle_webhook: message 事件，文字是"綁定"，且已綁定，應呼叫 send_already_bound_msg
@patch("services.webhook_service.LineBindingUser.query")
@patch("services.webhook_service.send_bind_url")
@patch("services.webhook_service.send_already_bound_msg")
def test_handle_webhook_message_bind_bound(mock_already_bound_msg, mock_bind_url, mock_filter_by):
    # 先 mock filter_by().first() 返回一個非 None 物件，表示已綁定
    mock_filter_by.return_value.first.return_value = object()

    event = {
        "events": [
            {
                "type": "message",
                "replyToken": "rtoken",
                "source": {"userId": "U123"},
                "message": {"text": "綁定"}
            }
        ]
    }

    result = handle_webhook(event, "token")

    # 斷言 send_already_bound_msg 有被呼叫一次，且帶入參數正確
    mock_already_bound_msg.assert_called_once_with("rtoken")
    # 斷言 send_bind_url 沒有被呼叫
    mock_bind_url.assert_not_called()

# 測試 handle_webhook: message 一般訊息，已綁定，應成功呼叫 reply API
@patch("services.webhook_service.LineBindingUser.query")
@patch("services.webhook_service.handle_message", return_value="回覆訊息")
@patch("services.webhook_service.build_payload")
@patch("services.webhook_service.requests.post")
@patch("services.webhook_service.load_session")
@patch("services.webhook_service.save_session")
def test_handle_webhook_message_general_bound(
    mock_save, mock_load, mock_requests_post, mock_build_payload,
    mock_handle_message, mock_filter_by
):
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock(return_value=None)
    mock_response.url = "https://api.line.me/v2/bot/message/reply"
    mock_requests_post.return_value = mock_response

    mock_filter_by.return_value.first.return_value = object()  # 已綁定
    mock_load.return_value = {}
    mock_build_payload.return_value = {
        "replyToken": "rtoken",
        "messages": [{"type": "text", "text": "回覆訊息"}]
    }

    event = {
        "events": [
            {
                "type": "message",
                "replyToken": "rtoken",
                "source": {"userId": "U123"},
                "message": {"text": "一般訊息"}
            }
        ]
    }
    result = handle_webhook(event, "token")

    assert result["status"] == "success"
    mock_handle_message.assert_called_once()
    mock_build_payload.assert_called_once()
    mock_requests_post.assert_called_once()
    mock_load.assert_called_once()
    mock_save.assert_called_once()

# 測試 handle_webhook: message 一般訊息，未綁定，應回覆請先綁定
@patch("services.webhook_service.LineBindingUser.query")
@patch("services.webhook_service.requests.post")
@patch("services.webhook_service.load_session")
@patch("services.webhook_service.save_session")
def test_handle_webhook_message_general_unbound(
    mock_save, mock_load, mock_requests_post, mock_filter_by
):
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock(return_value=None)
    mock_response.url = "https://api.line.me/v2/bot/message/reply"
    mock_requests_post.return_value = mock_response

    mock_filter_by.return_value.first.return_value = None  # ❌未綁定帳號
    mock_load.return_value = {}

    event = {
        "events": [
            {
                "type": "message",
                "replyToken": "rtoken",
                "source": {"userId": "U123"},
                "message": {"text": "一般訊息"}
            }
        ]
    }
    result = handle_webhook(event, "token")

    assert result["status"] == "success"
    mock_requests_post.assert_called_once()
    mock_load.assert_called_once()
    mock_save.assert_called_once()