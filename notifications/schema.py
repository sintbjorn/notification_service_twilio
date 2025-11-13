import strawberry
from typing import Optional
from .models import Notification, User
from .services.producer import enqueue_notification

@strawberry.type
class NotificationType:
    id: strawberry.ID
    status: str
    subject: str
    message: str

@strawberry.type
class Query:
    @strawberry.field
    def notification(self, id: int) -> Optional[NotificationType]:
        n = Notification.objects.filter(pk=id).first()
        if not n:
            return None
        return NotificationType(id=n.id, status=n.status, subject=n.subject, message=n.message)

@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_notification(self, user_id: int, message: str, subject: str = "", idempotency_key: Optional[str] = None) -> NotificationType:
        user = User.objects.get(pk=user_id)
        n = enqueue_notification(user=user, subject=subject, message=message, idempotency_key=idempotency_key)
        return NotificationType(id=n.id, status=n.status, subject=n.subject, message=n.message)

schema = strawberry.Schema(query=Query, mutation=Mutation)
