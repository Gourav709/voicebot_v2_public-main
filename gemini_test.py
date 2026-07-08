from google import genai

# The client gets the API key from the environment variable `GEMINI_API_KEY`.

#GEMINI_API_KEY = "AIzaSyCmn4K_2EaWG2-fkVps71mBllBta4bsjio"
client = genai.Client(api_key="AIzaSyCmn4K_2EaWG2-fkVps71mBllBta4bsjio")

response = client.models.generate_content(
    model="gemini-3-flash-preview", contents="tell me a joke about Data scientiest in hindi but in english typescript?"
)
print(response.text)