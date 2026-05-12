from source.config.logging import logger
from dataclasses import dataclass
from typing import Optional

from source.common.error import ApplicationError
from source.types.model_id import ModelIdType
from source.types.model_id_uuid import ModelIdUuidType


@dataclass(eq=False)
class GeneralCustomError(ApplicationError):
    text: str
    model_name: Optional[str] = None
    error: Optional[str] = None
    model_id: Optional[ModelIdType | ModelIdUuidType] = None
    log_warn: Optional[str] = None

    @property
    def message(self):
        log_text = f":=GCE| Model={self.model_name}, id={self.model_id}, text={self.text}, error={self.error}"
        logger.debug(log_text)
        if self.log_warn:
            logger.warning(self.log_warn)
        return log_text

    def __str__(self):
        return self.message
