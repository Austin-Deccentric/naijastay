from datetime import date

from pydantic import BaseModel


class OccupancyReport(BaseModel):
    report_date: date
    total_rooms: int
    occupied_rooms: int
    available_rooms: int
    dirty_rooms: int
    occupancy_rate: float