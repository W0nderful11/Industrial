import json
from typing import Optional

from .base_analyzer import BaseAnalyzer


class LogAnalyzer(BaseAnalyzer):
    def load_and_parse_file(self) -> None:
        try:
            with open(self.path, "r", encoding='utf-8') as file:
                self.log = file.read()
            text = "".join(self.log.split("\n")[1:])
            self.log_dict = json.loads(text)
        except Exception as e:
            print(f"Error parsing IPS file: {e}")
            self.log_dict = {} 