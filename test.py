import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

try:
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Тестовое сообщение"}]
    )
    print(response)
except openai.error.OpenAIError as e:
    print(f"Ошибка OpenAI: {e}")
