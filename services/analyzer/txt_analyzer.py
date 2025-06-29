import json
import re
from typing import Dict, Optional

from .base_analyzer import BaseAnalyzer


class TxtAnalyzer(BaseAnalyzer):
    def __init__(self, lang: str, path: Optional[str] = None, username: Optional[str] = None):
        super().__init__(lang, path, username)

    def _normalize_json_content(self, content: str) -> str:
        content = re.sub(r'\s*(\w+)\s*:', r'\1:', content)
        content = re.sub(r'\s*([:,])\s*', r'\1', content)
        content = re.sub(r'("\s+)|(\s+")', '"', content)
        return content

    def _parse_json_content(self, content: str) -> Dict:
        try:
            normalized_content = self._normalize_json_content(content)
            return json.loads(normalized_content)
        except json.JSONDecodeError:
            combined_data = {}
            try:
                if "}{" in content:
                    parts = content.split("}{")
                    first_part = parts[0] + "}"
                    second_part = "{" + parts[1]
                    combined_data.update(json.loads(self._normalize_json_content(first_part)))
                    combined_data.update(json.loads(self._normalize_json_content(second_part)))
                    return combined_data

                lines = content.splitlines()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(self._normalize_json_content(line))
                        if isinstance(data, dict):
                            combined_data.update(data)
                    except json.JSONDecodeError:
                        continue
                return combined_data
            except Exception:
                return {}

    def _extract_panic_info(self, content: str) -> Dict:
        result = {}

        panic_patterns = [
            r'panic\(.*?\):\s*(.*?)(?:\n|$)',
            r'panicString["\s:]+([^"\n]+)',
            r'Panic\s+occurred["\s:]+([^"\n]+)',
            r'error["\s:]+([^"\n]+)'
        ]
        for pattern in panic_patterns:
            if match := re.search(pattern, content, re.IGNORECASE):
                result['panicString'] = match.group(1).strip()
                break

        product_patterns = [
            r'[Pp]roduct["\s:]+([^"\n]+)',
            r'[Dd]evice["\s:]+([^"\n]+)',
            r'[Mm]odel["\s:]+([^"\n]+)'
        ]
        for pattern in product_patterns:
            if match := re.search(pattern, content, re.IGNORECASE):
                result['product'] = match.group(1).strip()
                break

        return result

    def _clean_content(self, content: str) -> str:
        content = content.encode('utf-8').decode('utf-8-sig')
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        content = content.replace('\x00', '').replace('\ufeff', '')

        content = re.sub(r'(?<=\w)\s(?=\w)', '', content)
        return content.strip()

    def load_and_parse_file(self) -> None:
        try:
            encodings = ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']
            content = None

            for encoding in encodings:
                try:
                    with open(self.path, 'r', encoding=encoding) as file:
                        content = file.read()
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                raise ValueError("Could not decode file with any supported encoding")

            content = self._clean_content(content)
            self.log = content

            json_data = self._parse_json_content(content)

            if not json_data:
                json_data = self._extract_panic_info(content)

            if not json_data.get('panicString') and not json_data.get('product'):
                fallback_data = self._extract_panic_info(content)
                json_data.update(fallback_data)

            self.log_dict = json_data

            if self.log_dict:
                print("Successfully parsed file content")
                print(json.dumps(self.log_dict, indent=2, ensure_ascii=False))

        except Exception as e:
            print(f"Error parsing file: {e}")
            self.log_dict = {} 