from contextvars import ContextVar

current_request = ContextVar("current_request", default=None)
