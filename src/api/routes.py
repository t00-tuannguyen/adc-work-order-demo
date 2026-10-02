"""Gom router theo context. Contract: specs/api-contracts.md — đổi contract ở đó TRƯỚC khi sửa code.

Còn thiếu (theo backlog): KPI T-044–T-046.
Router `/auth/*` (ADC-008) gắn ở gốc trong `src/main.py`.
"""

from fastapi import APIRouter

from src.api import approval, auth, demo, estimation, incidents, intake, intake_review, risk, scheduling, users

router = APIRouter()
router.include_router(estimation.router)
router.include_router(demo.router)
router.include_router(intake.router)
router.include_router(intake_review.router)
router.include_router(scheduling.router)
router.include_router(incidents.router)
router.include_router(risk.router)
router.include_router(approval.router)
router.include_router(auth.me_router)
router.include_router(users.router)
