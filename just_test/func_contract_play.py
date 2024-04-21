import functools
from typing import Callable, Any

import pydantic
from annotated_types import Predicate
from dotenv import load_dotenv

from typing import Annotated, get_type_hints, Callable

import marvin
import inspect

from pydantic import BaseModel, Field, type_adapter

import marvin
from marvin.settings import temporary_settings

load_dotenv()





def contract(func: Callable, pre: Callable = None, post: Callable = None) -> Callable:
    pre = lambda *args, **kwargs: True if pre is None else pre  # noqa E731
    post = lambda *args, **kwargs: True if post is None else post  # noqa E731

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        hints = get_type_hints(func, include_extras=True)
        signature = inspect.signature(func)

        new_args = []
        new_kwargs = {}

        # Merge args and kwargs into a single dictionary for easier processing
        bound_arguments = signature.bind(*args, **kwargs)
        bound_arguments.apply_defaults()
        all_arguments = bound_arguments.arguments
        for name, value in all_arguments.items():
            if name in hints:
                # Use TypeAdapter for the parameter annotation to validate and/or coerce the value
                adapter = type_adapter.TypeAdapter(
                    signature.parameters[name].annotation
                )
                # For TypeAdapter, `validate_python` both validates and coerces the value
                coerced_value = adapter.validate_python(value)
                # Determine if the parameter should be treated as positional or keyword argument
                if name in signature.parameters and signature.parameters[name].kind in (
                    signature.parameters[name].POSITIONAL_ONLY,
                    signature.parameters[name].POSITIONAL_OR_KEYWORD,
                ):
                    new_args.append(coerced_value)
                else:
                    new_kwargs[name] = coerced_value
            else:
                # No specific type hint for this parameter, pass it as is
                if name in signature.parameters and signature.parameters[name].kind in (
                    signature.parameters[name].POSITIONAL_ONLY,
                    signature.parameters[name].POSITIONAL_OR_KEYWORD,
                ):
                    new_args.append(value)
                else:
                    new_kwargs[name] = value
        if not pre(*new_args, **new_kwargs):
            raise pydantic.ValidationError("Failed Pre condition of contract")

        # Call the original function with coerced values
        result = func(*new_args, **new_kwargs)

        if "return" in hints and hints["return"] is not None:
            return_adapter = type_adapter.TypeAdapter(hints["return"])
            result = return_adapter.validate_python(result)

        new_args = [result] + new_args
        if not post(*new_args, **new_kwargs):
            raise pydantic.ValidationError("Failed post condition of contract")
        return result

    return wrapper


@contract
def reply_comment(
    processed_comment: Annotated[
        str,
        Predicate(
            marvin.val_contract("must not contain words inappropriate for children")
        ),
    ],
    **kwargs: dict,
) -> str:
    # ....
    return processed_comment


with temporary_settings(ai__text__disable_contract=False):
    # print(marvin.val_contract("must add up to 2")(1, 1))
    # print(marvin.val_contract("must add up to 2")(1, 2))
    print(reply_comment("fuck this shit"))


@contract(
    pre=lambda comment, reply: marvin.val_contract(
        "the comment and reply must be related and not off topic"
    )(comment=comment, reply=reply),
    post=lambda result, comment, reply: True,
)
def process_comment(comment: str, reply: str) -> str:
    pass
