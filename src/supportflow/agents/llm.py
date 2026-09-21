from langchain.chat_models import init_chat_model

from supportflow.core.config import settings


chat_model = init_chat_model(
    model=settings.DEEPSEEK_MODEL,
    model_provider="deepseek",
    api_key=settings.DEEPSEEK_API_KEY,
    api_base=settings.DEEPSEEK_BASE_URL,
)

if __name__ == "__main__":
    response=chat_model.invoke("hello")
    print(response.content)
