from source.config.logging import logger
from dataclasses import dataclass
from typing import Optional

from source.common.error import ApplicationError
from source.types.model_id import ModelIdType
from source.types.model_id_uuid import ModelIdUuidType


@dataclass(eq=False)
class CustomDoesNotExist(ApplicationError):
    class_name: str
    model_id: Optional[ModelIdUuidType | ModelIdType] = None

    @property
    def message(self):
        text = f"Объект {self.class_name} с идентификатором {self.model_id} не найден"
        logger.warning(text)
        return text
