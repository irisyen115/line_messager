import pytest
from unittest.mock import MagicMock, call, patch
import threading
from services.message_handler import handle_person_selection, upload_sequence

# 假的 do_upload 函式，用來觀察被呼叫狀況
def mock_do_upload(person_id, album_name, num_photos, user_id, session, session_data, user_states, token):
    print(f"上傳 {num_photos} 張給 {person_id}")

# 假的 Thread，直接同步執行 upload_sequence 方便測試
class DummyThread:
    def __init__(self, target, args):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)

@pytest.fixture
def fake_state():
    return {
        "selected_person_ids": ["1", "2", "3"],
        "album_name": "測試相簿",
        "num_photos": 10,
        "step": "selecting",
        "is_uploading": False
    }

@pytest.fixture
def user_states():
    return {}

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
def mock_session_data():
    return MagicMock()

@patch("threading.Thread", DummyThread)  # 用假 Thread 同步執行
def test_handle_person_selection完成選擇時啟動上傳(fake_state, user_states, mock_session, mock_session_data):
    # 定義 user_id 與假 token
    user_id = "U123"
    token = "fake-token"

    # Patch do_upload，觀察是否被呼叫
    mock_upload = MagicMock()

    # 傳入 "完成選擇"
    result = handle_person_selection(
        user_id,
        "完成選擇",
        fake_state,
        mock_session,
        mock_session_data,
        token
    )

    # 啟動 upload_sequence（這裡會自動透過 DummyThread 執行）
    upload_sequence(fake_state, user_id, mock_session, mock_session_data, user_states, token, mock_upload)

    # 確認訊息正確
    assert "正在上傳" in result

    # 確認 do_upload 被呼叫 3 次（3 個人）
    assert mock_upload.call_count == 3

    # 檢查分配張數是否為 3+3+4（總共10張，平均3，最後一位多1張）
    expected_calls = [
        call("1", "測試相簿", 3, user_id, mock_session, mock_session_data, user_states, token),
        call("2", "測試相簿", 3, user_id, mock_session, mock_session_data, user_states, token),
        call("3", "測試相簿", 4, user_id, mock_session, mock_session_data, user_states, token),
    ]
    mock_upload.assert_has_calls(expected_calls, any_order=False)

    # 檢查上傳狀態
    assert fake_state["is_uploading"] is False
    assert fake_state["step"] == "done"
    assert user_states[user_id] == fake_state
