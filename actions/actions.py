from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher


import re
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher


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

        # Tìm tất cả các số
        numbers = re.findall(r'\d+', user_message)

        if not numbers:
            print("[NEW CODE] Không tìm thấy số!")
            dispatcher.utter_message(text="Bạn vui lòng cho biết rõ số điều bạn muốn tra cứu nhé.")
            return []

        dieu = numbers[0]
        print(f"[NEW CODE] Điều số tìm thấy: {dieu}")

        # Chuẩn hóa message - bỏ dấu, lowercase
        def normalize_text(text):
            """Chuẩn hóa văn bản: bỏ dấu tiếng Việt, lowercase"""
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
        print(f"[NEW CODE] Normalized: '{user_normalized}'")

        # Nhận dạng văn bản với regex SIÊU LINH HOẠT

        # ===== NGHỊ ĐỊNH =====
        # Match: nghị định, nghi dinh, nđ, nd, ngh dinh, nghi dịnh, nghị đinh...
        nghi_dinh_patterns = [
            r'ngh?[ie]?\s*d[ie]?nh',  # nghi dinh, ngh dinh, nghidinh
            r'n[dđ]\s*\d+',  # nd105, nđ 105
            r'n[dđ][-\s]?cp',  # nd-cp, nđ cp
        ]

        is_nghi_dinh = any(re.search(pattern, user_normalized) for pattern in nghi_dinh_patterns)

        # ===== THÔNG TƯ =====
        # Match: thông tư, thong tu, tt, thông tu, thong tư...
        thong_tu_patterns = [
            r'th[oô]?ng?\s*t[uư]',  # thong tu, thông tư, thng tu
            r'tt\s*\d+',  # tt38, tt 38
            r'tt[-\s]?bca',  # tt-bca, tt bca
        ]

        is_thong_tu = any(re.search(pattern, user_normalized) for pattern in thong_tu_patterns)

        # ===== LUẬT =====
        # Match: luật, luat, l, pccc, phòng cháy, phong chay...
        luat_patterns = [
            r'lu[aậ]?t',  # luật, luat, luât, lut
            r'\bl\b',  # " l " (chữ l riêng lẻ)
            r'pccc',
            r'ph[oò]?ng\s*ch[aá]y',  # phòng cháy, phong chay
        ]

        is_luat = any(re.search(pattern, user_normalized) for pattern in luat_patterns)

        # Quyết định văn bản (ưu tiên: Nghị định > Thông tư > Luật)
        if is_nghi_dinh:
            file_path = "data/files/nghi_dinh_105_2025.txt"
            doc_name = "Nghị định 105/2025/NĐ-CP"
        elif is_thong_tu:
            file_path = "data/files/thong_tu_38_2025.txt"
            doc_name = "Thông tư 38/2025/TT-BCA"
        else:
            # Mặc định: Luật PCCC (kể cả khi không có từ khóa)
            file_path = "data/files/luat_pccc_2024.txt"
            doc_name = "Luật Phòng cháy, chữa cháy và Cứu nạn, cứu hộ 2024"

        print(f"[NEW CODE] Document: {doc_name}")

        # Pattern tìm Điều trong file
        pattern = fr"Điều\s+{dieu}\..*?(?=Điều\s+\d+\.|$)"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()

            print(f"[NEW CODE] Đọc file thành công, độ dài: {len(text)} ký tự")

            match = re.search(pattern, text, re.DOTALL)

            if match:
                section = match.group(0).strip()
                print(f"[NEW CODE] Tìm thấy! Độ dài: {len(section)} ký tự")

                dispatcher.utter_message(text=f"📄 {doc_name}\n\n{section}")
            else:
                print(f"[NEW CODE] KHÔNG tìm thấy Điều {dieu}")
                dispatcher.utter_message(text=f"Không tìm thấy Điều {dieu} trong {doc_name}.")

        except FileNotFoundError:
            print(f"[NEW CODE] LỖI: Không tìm thấy file {file_path}")
            dispatcher.utter_message(text="⚠️ Không tìm thấy file luật")
        except Exception as e:
            print(f"[NEW CODE] LỖI: {e}")
            dispatcher.utter_message(text=f"❌ Lỗi: {e}")

        return []


