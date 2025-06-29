#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re

def clean_po_file(filepath):
    """Удаляет дублированные msgid из po файла."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Разбиваем на блоки по msgid
    blocks = re.split(r'\n(?=msgid )', content)
    
    seen_msgids = set()
    clean_blocks = []
    
    for i, block in enumerate(blocks):
        if i == 0:  # Первый блок - заголовок
            clean_blocks.append(block)
            continue
            
        # Извлекаем msgid из блока
        lines = block.split('\n')
        msgid_lines = []
        
        for line in lines:
            if line.startswith('msgid ') or (msgid_lines and line.startswith('"')):
                msgid_lines.append(line)
            elif msgid_lines:  # Закончились строки msgid
                break
        
        msgid_key = '\n'.join(msgid_lines)
        
        if msgid_key not in seen_msgids:
            seen_msgids.add(msgid_key)
            clean_blocks.append(block)
        else:
            print(f"Удален дубликат: {msgid_lines[0][:50]}...")
    
    # Собираем обратно
    clean_content = '\n'.join(clean_blocks)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(clean_content)
    
    print(f"Файл {filepath} очищен от дубликатов")

if __name__ == '__main__':
    clean_po_file('locales/en/LC_MESSAGES/messages.po') 