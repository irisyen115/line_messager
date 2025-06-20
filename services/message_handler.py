import threading
from linebot.models import FlexSendMessage
from utils.flex_message_builder import build_face_bubbles, get_album_name_input_options
from services.request_service import do_upload, get_album_list, get_faces
from config.config import Config
import logging
import requests
from dotenv import load_dotenv
from linebot import LineBotApi
from linebot.models import TextSendMessage, QuickReply, QuickReplyButton, MessageAction, BubbleContainer, CarouselContainer

load_dotenv()

session = requests.Session()

logging.basicConfig(filename="error.log", level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")
line_bot_api = LineBotApi(Config.LINE_CHANNEL_ACCESS_TOKEN)

VALID_TRANSITIONS = {
    None: ["ask_person", "start"],
    "ask_person": ["ask_person_again", "ask_google_album_name", "uploading"],
    "ask_google_album_name": ["ask_count"],
    "ask_count": ["uploading"],
    "uploading": [],
}

def is_valid_transition(current_step, next_step):
    return next_step in VALID_TRANSITIONS.get(current_step, [])

def set_user_step(user_id, state, next_step):
    if not is_valid_transition(state.get("step"), next_step):
        raise ValueError(f"非法狀態轉移：{state.get('step')} ➜ {next_step}")
    state["step"] = next_step
    user_states[user_id] = state

user_states = {}

def handle_message(user_id, message_text, session, session_data, token):
    try:
        state = user_states.setdefault(user_id, {
            "step": None,
            "faces": [],
            "faces_loading": False,
            "selected_person_ids": [],
            "is_uploading": False,
        })
        current_step = state.get("step")
        if current_step not in VALID_TRANSITIONS:
            return "⚠️ 發生錯誤，請重新開始流程。"

        if current_step:
            logging.error(f"Current step: {state['step']}")

        if message_text == "使用自訂參數":
            set_user_step(user_id, state, "ask_person")
            return handle_custom_parameters(user_id)

        elif message_text == "我要上傳照片":
            set_user_step(user_id, state, "ask_person")
            return handle_start_upload(user_id)

        if message_text == "列出我的相簿":
            return handle_list_albums(user_id, token)

        elif message_text == "手動輸入相簿名":
            return "🔤 請輸入相簿名稱："

        if current_step  == "ask_person":
            return handle_person_selection(user_id, message_text, state, session, session_data, token)

        elif current_step  == "ask_google_album_name":
            set_user_step(user_id, state, "ask_count")
            return handle_album_name_input(user_id, message_text, state)

        elif current_step  == "ask_count":
            set_user_step(user_id, state, "uploading")
            return handle_photo_count_input(user_id, message_text, state, session, session_data, token)

        return "請輸入「我要上傳照片」來開始相簿上傳流程。"

    except Exception as e:
        logging.error(e)
        return "⚠️ 發生錯誤，請稍後再試。"

def handle_list_albums(user_id, token):
    threading.Thread(target=get_album_list, args=(token, user_id)).start()
    return "📂 正在列出所有相簿，請稍候..."

def handle_custom_parameters(user_id):
    state = user_states.get(user_id, {})
    faces = state.get("faces", [])
    faces_loading = state.get("faces_loading", False)

    if not faces:
        if not faces_loading:
            state.update({
                "faces_loading": True
            })
            threading.Thread(target=get_faces, args=(session, user_id, user_states)).start()
            user_states[user_id] = state
            logging.error(f"user_states:{user_states[user_id]}")
            return "⚠️ 正在取得人物列表，完成後會通知您。"
        else:
            return "⚠️ 人物列表仍在載入中，請稍候..."

    carousel = {"type": "carousel", "contents": build_face_bubbles(faces)}
    return FlexSendMessage(alt_text="請選擇人物上傳照片", contents=carousel)

def handle_start_upload(user_id):
    state = user_states.setdefault(user_id, {})
    faces = state.get("faces", [])
    faces_loading = state.get("faces_loading", False)

    if not faces:
        if not faces_loading:
            state.update({
                "step": "ask_person",
                "album_name": "",
                "num_photos": 5,
                "faces_loading": True
            })
            threading.Thread(target=get_faces, args=(session, user_id, user_states)).start()
            user_states[user_id] = state
            return "⚠️ 正在取得人物列表，完成後會通知您。"
        else:
            return "⚠️ 人物列表仍在載入中，請稍候..."

    flex_msg = build_face_bubbles(faces)
    if isinstance(flex_msg.contents, CarouselContainer):
        for i, bubble in enumerate(flex_msg.contents.contents):
            if isinstance(bubble, BubbleContainer):
                contents = bubble.body.contents
                for j, content in enumerate(contents):
                    if content is None:
                        logging.error(f"Null element found in contents[{i}].body.contents[{j}]")
            else:
                logging.error(f"Unexpected bubble type at index {i}: {type(bubble)}")
    else:
        logging.error("flex_msg.contents is not a CarouselContainer")

    return flex_msg

def extract_person_id_from_text_or_action(message_text, state):
    if message_text.startswith("SELECT_PERSON_"):
        return message_text.replace("SELECT_PERSON_", "")
    # 也可以對應名字找 personId
    for face in state.get("faces", []):
        if face["name"] == message_text:
            return face["ID"]
    return None

def upload_sequence(state, user_id, session, session_data, user_states, token, do_upload):
    persons = state["selected_person_ids"]
    total_photos = state["num_photos"]
    n = len(persons)
    base_num = total_photos // n
    remainder = total_photos % n

    for i, person_id in enumerate(persons):
        num_to_upload = base_num + (remainder if i == n - 1 else 0)

        if num_to_upload > 0:
            do_upload(person_id, state["album_name"], num_to_upload,
                      user_id, session, session_data, user_states, token)

    state["is_uploading"] = False
    state["step"] = "done"
    user_states[user_id] = state


def handle_person_selection(user_id, message_text, state, session, session_data, token):
    if message_text.startswith("SELECT_PERSON_"):
        person_id = extract_person_id_from_text_or_action(message_text, state)
        if not person_id or not person_id.isdigit():
            return "❌ 請提供有效的人物 ID"
        logging.error(f"selected_person_ids: {state['selected_person_ids']}")
        if person_id not in state["selected_person_ids"]:
            state["selected_person_ids"].append(person_id)

        return f"✅ 已選擇 {len(state['selected_person_ids'])} 位人物，可繼續選擇或輸入『完成選擇』繼續下一步。"

    elif message_text == "完成選擇":
        if not state["selected_person_ids"]:
            return "⚠️ 請至少選擇一位人物再進行下一步。"

        if "album_name" in state and "num_photos" in state:
            if state.get("is_uploading"):
                return "⚠️ 照片正在上傳中，請稍候完成後再試一次。"

            state["step"] = "uploading"
            user_states[user_id] = state

            threading.Thread(
                target=upload_sequence,
                args=(state, user_id, session, session_data, user_states, token, do_upload)
            ).start()
            return f"✅ 收到資訊！正在上傳 {state['num_photos']} 張照片到相簿，請稍候..."
        else:
            set_user_step(user_id, state, "ask_google_album_name")
            return get_album_name_input_options()
    else:
        return "請點選選單上的「選擇」按鈕選擇人物，或輸入『完成選擇』繼續。"

def handle_photo_count_input(user_id, message_text, state, session, session_data, token):
    if not message_text.isdigit():
        return "❌ 請輸入正確的數字"
    num_photos = int(message_text)

    if state["is_uploading"]:
        return "⚠️ 照片正在上傳中，請稍候完成後再試一次。"

    state["num_photos"] = num_photos
    state["is_uploading"] = True
    user_states[user_id] = state

    threading.Thread(
        target=upload_sequence,
        args=(state, user_id, session, session_data, user_states, token, do_upload)
    ).start()

    return f"✅ 正在為 {len(state['selected_person_ids'])} 位人物，上傳 {num_photos} 張照片到相簿中，請稍候..."

def handle_album_name_input(user_id, message_text, state):
    state["album_name"] = message_text
    user_states[user_id] = state
    message = TextSendMessage(
        text="請選擇要上傳的照片張數：",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="5 張", text="5")),
            QuickReplyButton(action=MessageAction(label="50 張", text="50")),
            QuickReplyButton(action=MessageAction(label="100 張", text="100")),
            QuickReplyButton(action=MessageAction(label="200 張", text="200")),
        ])
    )
    try:
        return [message.as_json_dict()]
    except requests.RequestException as e:
        logging.error(f"回覆使用者時發生錯誤: {e}")
