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


@marvin.fn
def rating_for_customer(customer_profile: str) -> Callable[[str], int]:
    """
    Args:
        customer_profile: the preferences of the customer
    Returns:
        a function that specializes on the customer_profile to give a rating of a product between 1 to 10.
    """
    pass


# rating_func = rating_for_customer(
#     "asian lady who cares about quality but cost is of greater concern"
# )
# rt = rating_func("A wonderful blender that is only $19, on sale from $100")  # return 8


class Location(BaseModel):
    city: str = Field(description="City of life ")
    state: str = Field(description="State of affairs")


def weather_at_city(city: str) -> str:
    if city == "San Francisco":
        return "Sunny and bright"
    if city == "Los Angeles":
        return "Cold and Cloudy"


@marvin.fn
def pleasantness(attraction: str, weather_func: Callable[[str], str]) -> str:
    """
    Args:
        attraction: the name of the attraction in some place
        weather_func: a function that get the weather at a particular **city** that the attraction is located.
    Returns:
        How pleasant the attraction will likely be given the weather between 0 and 10
    """
    pass


# the weather in SF is really good rn, LA not so much
pleasantness("The Golden Gate Bridge", weather_at_city)  # return 8
pleasantness("Hollywood Sign", weather_at_city)  # return 2
