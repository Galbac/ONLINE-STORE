from pydantic import BaseModel


class ReferralResponse(BaseModel):
    code: str
    link: str
    reward_amount: int = 500
    invited_count: int = 0
    earned_points: int = 0
