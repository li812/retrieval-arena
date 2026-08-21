from google import genai

from app.schemas import ModelInfo, ValidateKeyResponse


class ModelConfigAgent:
    def validate_and_list_models(self, api_key: str) -> ValidateKeyResponse:
        try:
            client = genai.Client(api_key=api_key)
            models = list(client.models.list())

            gen_models: list[ModelInfo] = []
            embed_models: list[ModelInfo] = []

            for model in models:
                actions = getattr(model, "supported_actions", []) or []
                info = ModelInfo(
                    name=model.name,
                    display_name=getattr(model, "display_name", model.name),
                )
                if "generateContent" in actions:
                    gen_models.append(info)
                if "embedContent" in actions:
                    embed_models.append(info)

            return ValidateKeyResponse(
                valid=True,
                gen_models=gen_models,
                embed_models=embed_models,
            )
        except Exception as e:
            return ValidateKeyResponse(valid=False, error=str(e))
