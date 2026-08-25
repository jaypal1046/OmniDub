import requests

response = requests.post(
    'https://api.aimlapi.com/v1/chat/completions',
    headers={
        'Authorization': 'Bearer <YOUR_AIMLAPI_KEY>',
        'Content-Type': 'application/json',
    },
    json={
      "model": "openai/gpt-5-5",
      "messages": [
        {
          "role": "user",
          "content": "Give me three impressive things I can build with an API that serves 1000+ AI models."
        }
      ]
    },
)
print(response.json())