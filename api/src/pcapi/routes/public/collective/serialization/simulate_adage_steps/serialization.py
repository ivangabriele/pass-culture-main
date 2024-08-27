from pcapi.routes.serialization import BaseModel


class AdageId(BaseModel):
    uai: str
    redactor_id: int
