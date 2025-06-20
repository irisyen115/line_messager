import pytest
from unittest.mock import patch, MagicMock, mock_open
from services.request_service import do_upload, get_faces, get_album_list
from unittest.mock import ANY

@patch("services.request_service.line_bot_api.push_message")
@patch("services.request_service.json.dump")
@patch("services.request_service.open", new_callable=mock_open)
def test_do_upload_success(mock_open_file, mock_json_dump, mock_push):
    session = MagicMock()
    session.post.return_value.status_code = 200
    session.post.return_value.json.return_value = {"message": "成功"}
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = {}

    user_states = {}
    session_data = {}

    do_upload("p123", "test_album", 5, "U123", session, session_data, user_states, "token123")

    session.post.assert_called()
    session.get.assert_called()
    mock_push.assert_called_with("U123", ANY)
    mock_json_dump.assert_called()
    assert "U123" not in user_states

@patch("services.request_service.line_bot_api.push_message")
def test_do_upload_sync_photos_fail(mock_push):
    session = MagicMock()
    session.post.return_value.status_code = 500
    session.post.return_value.text = "Server Error"

    user_states = {"U123": {}}
    session_data = {}

    do_upload("p123", "album", 3, "U123", session, session_data, user_states, "token")

    mock_push.assert_called_with("U123", ANY)
    assert "U123" not in user_states


@patch("services.request_service.notify_user")
def test_get_faces_success(mock_notify):
    session = MagicMock()
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = [{"id": "1"}, {"id": "2"}]

    user_states = {"U123": {}}
    get_faces(session, "U123", user_states)

    assert user_states["U123"]["faces_loading"] is False
    assert len(user_states["U123"]["faces"]) == 2
    mock_notify.assert_called_with("U123", "✅ 人物列表已更新，共 2 位。")

@patch("services.request_service.notify_user")
def test_get_faces_error(mock_notify):
    session = MagicMock()
    session.get.side_effect = Exception("Connection failed")

    user_states = {"U123": {}}
    get_faces(session, "U123", user_states)

    assert user_states["U123"]["faces_loading"] is False
    mock_notify.assert_called_with("U123", "❌ 取得人物列表時發生錯誤。")

@patch("services.request_service.requests.post")
def test_get_album_list(mock_post):
    get_album_list("token123", "U123")
    mock_post.assert_called_once()
    assert mock_post.call_args[1]["params"] == {"token": "token123"}
    assert mock_post.call_args[1]["json"] == {"user_id": "U123"}
