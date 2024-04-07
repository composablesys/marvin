import functools
from typing import Callable, Any

import pydantic
from annotated_types import Predicate
from dotenv import load_dotenv

load_dotenv()
from typing import Annotated, get_type_hints, Callable

import marvin
import inspect

from pydantic import BaseModel, Field, type_adapter

import marvin
from marvin.settings import temporary_settings


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
        if not pre(*new_args,**new_kwargs):
            raise pydantic.ValidationError("Failed Pre condition of contract")

        # Call the original function with coerced values
        result = func(*new_args, **new_kwargs)

        if 'return' in hints and hints['return'] is not None:
            return_adapter = type_adapter.TypeAdapter(hints['return'])
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
    **kwargs: dict
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


# @marvin.fn
# def func(*data) -> bool:
#     """
#     Check whether the data provided satisfies this constraint:
#
#     The numbers must add up to 2
#
#     Args:
#         *data: data that you need to validate against the constraint
#
#     Returns:
#         a bool that represents if the data satisfies the constraint given
#     """
#     pass
#
#
# print(func(1, 1))

# @marvin.fn
# def rating_for_customer(customer_profile: str) -> Callable[[str], int]:
#     """
#     Args:
#         customer_profile: the preferences of the customer
#     Returns:
#         a function that specializes on the customer_profile to give a rating of a product between 1 to 10.
#     """
#     pass


# rating_func = rating_for_customer(
#     "asian lady who cares about quality but cost is of greater concern"
# )
# rt = rating_func("A wonderful blender that is only $19, on sale from $100")  # return 8


# class Location(BaseModel):
#     city: str = Field(description="City of life ")
#     state: str = Field(description="State of affairs")
#
#
# def weather_at_city(city: str) -> str:
#     if city == "San Francisco":
#         return "Sunny and bright"
#     if city == "Los Angeles":
#         return "Cold and Cloudy"
#
#
# @marvin.fn
# def pleasantness(attraction: str, weather_func: Callable[[str], str]) -> str:
#     """
#     Args:
#         attraction: the name of the attraction in some place
#         weather_func: a function that get the weather at a particular **city** that the attraction is located.
#     Returns:
#         How pleasant the attraction will likely be given the weather between 0 and 10
#     """
#     pass
#
#
# # the weather in SF is really good rn, LA not so much
# pleasantness("The Golden Gate Bridge", weather_at_city)  # return 8
# pleasantness("Hollywood Sign", weather_at_city)  # return 2

#
# class CallableWithMetaData(pydantic.BaseModel):
#     name: str
#     signature: inspect.Signature
#     docstring: Optional[str]
#     func: Optional[Callable]
#
#     class Config:
#         arbitrary_types_allowed = True
#
# CallableWithMetaData(name="name", signature=inspect.signature(rating_for_customer),docstring="asdskd",func=None)
# #
##
#
#
# #
# # print(a)
