from enum import Enum
from json import JSONEncoder
import typing


class EnumJSONEncoder(JSONEncoder):
    def default(self, obj: typing.Any) -> typing.Any:
        try:
            if isinstance(obj, Enum):
                return str(obj)
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)
