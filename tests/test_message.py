import pytest
from unittest.mock import patch, MagicMock
from services.message_handler import handle_message, handle_start_upload, user_states, handle_custom_parameters, set_user_step
from linebot.models import FlexSendMessage

@pytest.fixture
def clean_user_states():
    user_states.clear()
    yield
    user_states.clear()

@pytest.fixture
def user_id():
    return "user_123"

@pytest.fixture
def session():
    return MagicMock()

@pytest.fixture
def session_data():
    return {}

@pytest.fixture
def token():
    return "fake-token"

@patch("utils.flex_message_builder.build_face_bubbles")
def test_handle_start_upload_with_faces(mock_build_bubbles):
    user_id = "user_123"
    user_states[user_id] = {
        "faces": [{"name": "test", "img": "https://example.com/img.jpg", "ID": "abc123"}],
        "faces_loading": False,
    }
    mock_build_bubbles.return_value = FlexSendMessage(
        alt_text="請選擇人物上傳",
        contents={"type": "carousel", "contents": []}
    )

    result = handle_start_upload(user_id)

    # 檢查回傳是 FlexSendMessage 物件
    assert isinstance(result, FlexSendMessage)
    assert result.alt_text == "請選擇人物上傳"

@patch("services.message_handler.get_faces")
def test_handle_message_start_upload(mock_get_faces, clean_user_states):
    user_id = "user_123"
    message_text = "我要上傳照片"
    session = MagicMock()
    session_data = {}
    token = "fake-token"

    reply = handle_message(user_id, message_text, session, session_data, token)

    assert user_states[user_id]["step"] == "ask_person"
    assert user_states[user_id]["faces_loading"] == True
    assert "正在取得人物列表" in reply
    mock_get_faces.assert_called_once()


@patch("services.message_handler.get_faces")
def test_handle_custom_parameters_faces_loading(mock_get_faces, clean_user_states):
    user_id = "user_123"
    user_states[user_id] = {"step": "ask_person", "faces": [], "faces_loading": False}

    result = handle_custom_parameters(user_id)

    assert "正在取得人物列表" in result
    assert user_states[user_id]["faces_loading"] == True
    mock_get_faces.assert_called_once()

def test_invalid_transition(clean_user_states):
    user_id = "user_123"
    state = {"step": "uploading"}  # uploading 不能轉去 ask_person
    with pytest.raises(ValueError, match="非法狀態轉移"):
        set_user_step(user_id, state, "ask_person")

@patch("services.message_handler.threading.Thread")
def test_start_upload_triggers_face_fetch(mock_thread, user_id, session, session_data, token):
    user_states.pop(user_id, None)
    response = handle_message(user_id, "我要上傳照片", session, session_data, token)
    assert "取得人物列表" in response
    assert user_states[user_id]["step"] == "ask_person"
    assert mock_thread.called

def test_invalid_person_input(user_id, session, session_data, token):
    user_states[user_id] = {"step": "ask_person", "faces": [{"id": "123", "name": "test"}]}
    response = handle_message(user_id, "哈囉", session, session_data, token)
    assert "請點選選單" in response

@patch("services.message_handler.get_album_name_input_options")
def test_valid_person_input_then_go_to_ask_album(mock_album_opts, user_id, session, session_data, token):
    mock_album_opts.return_value = "請輸入相簿名稱"
    user_states[user_id] = {
        "step": "ask_person", "faces": [], "faces_loading": False,
        "person_id": "", "is_uploading": False
    }
    response = handle_message(user_id, "上傳 12345", session, session_data, token)
    assert "相簿名稱" in response
    assert user_states[user_id]["step"] == "ask_google_album_name"

def test_album_name_input_leads_to_quick_reply(user_id, session, session_data, token):
    user_states[user_id] = {"step": "ask_google_album_name"}
    response = handle_message(user_id, "我的相簿", session, session_data, token)
    assert isinstance(response, list)
    assert any("請選擇要上傳的照片張數" in d.get("text", "") for d in response)

def test_photo_count_input_invalid(user_id, session, session_data, token):
    user_states[user_id] = {"step": "ask_count", "album_name": "test", "person_id": "1", "is_uploading": False}
    response = handle_message(user_id, "abc", session, session_data, token)
    assert "請輸入正確的數字" in response

def test_album_list_request(user_id, session, session_data, token):
    response = handle_message(user_id, "列出我的相簿", session, session_data, token)
    assert "列出所有相簿" in response
