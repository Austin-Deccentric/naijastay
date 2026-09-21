from pydantic import BaseModel, PositiveFloat


class RoomTypeOut(BaseModel):
    name: str
    base_rate: int
    capacity: int

class RoomTypeUpdate(BaseModel):
    base_rate: PositiveFloat | None = None
    capacity: PositiveFloat | None = None

    model_config = {"extra":"forbid"}