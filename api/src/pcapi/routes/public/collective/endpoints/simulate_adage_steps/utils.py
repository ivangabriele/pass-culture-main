from functools import wraps
import typing

from pcapi import settings

from .errors import UnauthorizedEnvironment


def exclude_prod_environments(func: typing.Callable) -> typing.Callable:
    @wraps(func)
    def decorator(*args: typing.Sequence, **kwargs: typing.Mapping) -> typing.Any:
        if settings.IS_PROD or settings.IS_INTEGRATION:
            raise UnauthorizedEnvironment()
        return func(*args, **kwargs)

    return decorator
