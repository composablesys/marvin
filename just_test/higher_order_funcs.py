import functools
from typing import Callable, Any, Optional, List

import pydantic
from annotated_types import Predicate
from dotenv import load_dotenv

load_dotenv()

from typing import Annotated, get_type_hints, Callable

import marvin
import inspect

from pydantic import BaseModel, Field, type_adapter, schema_json_of

import marvin
from marvin.settings import temporary_settings


class NaturalLangType(BaseModel):
    other_information: Optional[str] = Field(
        default=None,
        description="Other information about the current data that could be "
        "relevant but is not otherwise captured by the other fields"
    )

    @classmethod
    def natural_lang_constraints(cls) -> List[str]:
        """
        This is a function where all child classes should override if they wish
        to declare additional natural language constraints. Note that the overridden class must
        call this method on the super() object to ensure that all constraints are populated appropriately
        from the parents unless explicitly overridden.
        """
        # super().natural_lang_constraints()
        return ["hi"]

    def func(self):
        return self.__class__.natural_lang_constraints()

class Sad(NaturalLangType):
    @classmethod
    def natural_lang_constraints(cls) -> List[str]:
        existing = super().natural_lang_constraints()
        return existing + ["hello"]

print(Sad.natural_lang_constraints())
print(Sad().func())
#
# @marvin.fn
# def rating_for_customer(customer_profile: str) -> Callable[[str], int]:
#     """
#     Args:
#         customer_profile: the preferences of the customer
#     Returns:
#         a function that specializes on the customer_profile to give a rating of a product between 1 to 10.
#     """
#     pass
#
#
# rating_func = rating_for_customer(
#     "asian lady who cares about quality but cost is of greater concern"
# )
# rt = rating_func("A wonderful blender that is only $19, on sale from $100")  # return 8
#
#
# class Location(BaseModel):
#     city: str = Field(description="City of life ")
#     state: str = Field(description="State of affairs")
#     comment: Annotated[
#         str,
#         Predicate(
#             marvin.val_contract("must not contain words inappropriate for children")
#         ),
#     ]
#
#
# print(Location.model_json_schema())
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
#
# application_profile = Profile(
#     name="Adam Smith",
#     education="Bachelor's in Data Science",
#     projects=["Building my own neural network at SpaceX", ...],
# )
# marvin.match(
#     application_profile,
#     ("Strong Experience in Data Science Particularly Feature Engineering", lambda: ...),
#     ("Have a degree in related field, but lacks real world projects", lambda: ...),
#     ("No relevant or very little relevant experience ", lambda: send_rejection_email()),
# )
