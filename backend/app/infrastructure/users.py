from ..core.models import RequestContext
from ..core.ports import UserResolver


class LocalUserResolver(UserResolver):
    async def resolve(self, context: RequestContext) -> RequestContext:
        return context
