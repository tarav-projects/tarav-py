"""Explicit boundary for the Models redesign."""


class ToImplementError(NotImplementedError):
    """An existing operation is disconnected pending its redesign."""


def require_models():
    raise ToImplementError("Models is disconnected pending redesign; retained data is unchanged.")
