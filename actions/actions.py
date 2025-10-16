import re
import requests
import logging
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

logger = logging.getLogger(__name__)

API_KEY = "AIzaSyB-KSP6j0I5MGX-Q1DcLsYUM7JNuu2YA4I"

class ActionReadLawSection(Action):
    def name(self) -> Text:
        return "action_read_law_section"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        user_message = tracker.latest_message.get('text', '')

        print(f"\n{'=' * 60}")
        print(f"[NEW CODE] User message: '{user_message}'")
        print(f"{'=' * 60}")

        numbers = re.findall(r'\d+', user_message)
        if not numbers:
            dispatcher.utter_message(text="Bạn vui lòng cho biết rõ số điều bạn muốn tra cứu nhé.")
            return []

        dieu = numbers[0]

        def normalize_text(text):
            replacements = {
                'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
                'ă': 'a', 'ắ': 'a', 'ằ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
                'â': 'a', 'ấ': 'a', 'ầ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
                'đ': 'd',
                'é': 'e', 'è': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
                'ê': 'e', 'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
                'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
                'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
                'ô': 'o', 'ố': 'o', 'ồ': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
                'ơ': 'o', 'ớ': 'o', 'ờ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
                'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
                'ư': 'u', 'ứ': 'u', 'ừ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
                'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
            }
            text = text.lower()
            for vn, en in replacements.items():
                text = text.replace(vn, en)
            return text

        user_normalized = normalize_text(user_message)

        nghi_dinh_patterns = [r'ngh?[ie]?\s*d[ie]?nh', r'n[dđ]\s*\d+', r'n[dđ][-\s]?cp']
        thong_tu_patterns = [r'th[oô]?ng?\s*t[uư]', r'tt\s*\d+', r'tt[-\s]?bca']
        luat_patterns = [r'lu[aậ]?t', r'\bl\b', r'pccc', r'ph[oò]?ng\s*ch[aá]y']

        is_nghi_dinh = any(re.search(p, user_normalized) for p in nghi_dinh_patterns)
        is_thong_tu = any(re.search(p, user_normalized) for p in thong_tu_patterns)
        is_luat = any(re.search(p, user_normalized) for p in luat_patterns)

        if is_nghi_dinh:
            file_path = "data/files/nghi_dinh_105_2025.txt"
            doc_name = "Nghị định 105/2025/NĐ-CP"
        elif is_thong_tu:
            file_path = "data/files/thong_tu_38_2025.txt"
            doc_name = "Thông tư 38/2025/TT-BCA"
        else:
            file_path = "data/files/luat_pccc_2024.txt"
            doc_name = "Luật Phòng cháy, chữa cháy và Cứu nạn, cứu hộ 2024"

        pattern = fr"Điều\s+{dieu}\..*?(?=Điều\s+\d+\.|$)"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()

            match = re.search(pattern, text, re.DOTALL)

            if match:
                section = match.group(0).strip()
                dispatcher.utter_message(text=f"📄 {doc_name}\n\n{section}")
            else:
                dispatcher.utter_message(text=f"Không tìm thấy Điều {dieu} trong {doc_name}.")
        except FileNotFoundError:
            dispatcher.utter_message(text="⚠️ Không tìm thấy file luật")
        except Exception as e:
            dispatcher.utter_message(text=f"❌ Lỗi: {e}")

        return []


class ActionCallGemini(Action):
    """Fallback action gọi Gemini API"""

    def name(self) -> Text:
        return "action_call_gemini"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        user_message = tracker.latest_message.get("text", "").strip()

        if not user_message:
            dispatcher.utter_message(text="Xin lỗi, tôi không hiểu. Bạn có thể nói lại không?")
            return []

        if not API_KEY:
            dispatcher.utter_message(text="Không có khóa API được cấu hình.")
            return []

        try:
            response_text = self._call_gemini(user_message)
            if response_text:
                dispatcher.utter_message(text=f"{response_text}")
            else:
                dispatcher.utter_message(text="Xin lỗi, tôi không hiểu. Bạn có thể diễn đạt lại không?")
        except Exception as e:
            logger.error(f"Lỗi khi gọi Gemini API: {e}")
            dispatcher.utter_message(text="Xin lỗi, tôi không hiểu. Bạn có thể diễn đạt lại không?")

        return []

    def _call_gemini(self, message: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": f"Trả lời ngắn gọn bằng tiếng Việt: {message}"}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 200},
        }
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
