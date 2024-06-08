import os

from openai import OpenAI

# Get the API key from the environment variable
api_key = os.getenv("OPEN_AI_KEY")
gateway = os.getenv("GATEWAY_TEST_URL")

if not api_key:
    raise ValueError("API key is not set. Please set the OPEN_AI_KEY environment variable.")

client = OpenAI(base_url=gateway, api_key=api_key)

completion = client.chat.completions.create(
    model="llama3",
    messages=[
        {
            "role": "user",
            "content": "Compose a poem that explains the concept of recursion in programming.",
        }
    ],
    stream=True,
)

# Print the completion
for chunk in completion:
    print(chunk.choices[0].delta.content, end="")
print()
