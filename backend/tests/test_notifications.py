from sqlalchemy import select

from app.auth.service import AuthService
from app.models.system import Notification
from app.notifications.engine import NotificationEngine


async def test_web_alert_is_persisted_when_redis_is_unavailable(db_session):
    user = await AuthService(db_session).create_user(
        email="alerts@example.com",
        username="alerts-owner",
        password="TestPass123!",
    )
    delivered = await NotificationEngine(db_session).send_alert(
        user.id,
        "Safety test",
        "Persist this alert",
        priority="critical",
    )
    notification = (
        await db_session.execute(
            select(Notification).where(Notification.user_id == user.id)
        )
    ).scalar_one()
    assert delivered["web"] is True
    assert notification.title == "Safety test"
    assert notification.priority == "critical"
    assert notification.delivered == {"database": True}
