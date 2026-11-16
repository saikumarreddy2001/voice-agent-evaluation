
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env", override=True)

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "user", "content": "Reply exactly: API WORKING"}
    ],
    max_tokens=10
)

print(response.choices[0].message.content)
