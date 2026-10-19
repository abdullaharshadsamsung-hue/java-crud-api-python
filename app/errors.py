"""Domain error types.

Port of ``com.smartContact.error.UserNotFoundException``. The HTTP mapping
(404 + ErrorMessage body) lives in the exception-handler module ported from
``RestResponseEntityExceptionHandling``; this module only defines the error.
"""

from __future__ import annotations

__all__ = ["UserNotFoundException"]


def _describe_cause(cause: BaseException) -> str:
    """Mirror Java's ``Throwable.toString()``: ``"ClassName: message"`` or ``"ClassName"``."""
    name = type(cause).__qualname__
    text = str(cause)
    return f"{name}: {text}" if text else name


class UserNotFoundException(Exception):
    """Raised when a requested user does not exist.

    Collapses the Java constructor overloads into one signature:

    * ``UserNotFoundException()`` – no message, no cause.
    * ``UserNotFoundException("msg")`` – message, no cause.
    * ``UserNotFoundException("msg", cause)`` – message and cause.
    * ``UserNotFoundException(cause)`` / ``UserNotFoundException.from_cause(cause)``
      – wraps ``cause``; message derived from it as Java does
      (``cause.toString()``).
    * ``enable_suppression`` / ``writable_stack_trace`` keyword-only flags stand in
      for the protected four-argument Java constructor.

    The cause is linked via ``__cause__`` so tracebacks show the chain, exactly
    like ``raise UserNotFoundException(...) from cause``.
    """

    def __init__(
        self,
        message: str | BaseException | None = None,
        cause: BaseException | None = None,
        *,
        enable_suppression: bool = True,
        writable_stack_trace: bool = True,
    ) -> None:
        # Java overload ``UserNotFoundException(Throwable cause)``.
        if isinstance(message, BaseException):
            if cause is not None:
                raise TypeError("cause given twice: positionally and as 'cause'")
            cause = message
            derived: str | None = _describe_cause(cause)
        else:
            derived = message

        if derived is None:
            super().__init__()
        else:
            super().__init__(derived)

        self._message: str | None = derived
        # MIGRATION_NOTE: Python has no equivalent of Java's suppressed-exception
        # list or non-writable stack traces, nor of `protected` access. These
        # flags are recorded for subclasses/introspection only and do not change
        # runtime behaviour.
        self.enable_suppression: bool = enable_suppression
        self.writable_stack_trace: bool = writable_stack_trace
        if cause is not None:
            self.__cause__ = cause

    @classmethod
    def from_cause(cls, cause: BaseException) -> UserNotFoundException:
        """Wrap ``cause``; the message is derived from it (Java ``Throwable(cause)``)."""
        return cls(cause)

    @property
    def message(self) -> str | None:
        """Equivalent of Java ``getMessage()``; ``None`` when no detail message."""
        return self._message

    @property
    def cause(self) -> BaseException | None:
        """Equivalent of Java ``getCause()``."""
        return self.__cause__

    def __str__(self) -> str:
        return self._message or ""
