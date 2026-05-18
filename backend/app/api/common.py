from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class ApiError(BaseModel):
    code: str = Field(..., description="Код ошибки, пригодный для автоматической обработки (например, 'invalid_parameters', 'not_found', 'internal_error').")
    message: str = Field(..., description="Человекочитаемое описание ошибки.")
    target: Optional[str] = Field(None, description="Идентификатор поля/ресурса, к которому относится ошибка (если применимо).")
    details: Optional[Dict[str, Any]] = Field(None, description="Дополнительные данные для диагностики.")
    request_id: Optional[str] = Field(None, description="Идентификатор запроса (X-Request-ID).")


    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "code": "invalid_parameters",
                    "message": "Поле 'progress' должно быть словарем {TopicUID: mastery}",
                    "target": "progress",
                    "details": {"expected_type": "object", "received": "array"},
                    "request_id": "req-8fda1c1a",
                }
            ]
        }
    }

class StandardResponse(BaseModel):
    items: List[Any]
    meta: Dict[str, Any] = {}
