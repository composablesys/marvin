from typing import Callable

from dotenv import load_dotenv

load_dotenv()

import marvin

from pydantic import BaseModel, Field


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


@marvin.fn
def where_is(attraction: str, weather: Callable[[str], str]) -> Location:
    """
    Args:
        attraction: the name of the attraction in some place
        weather: a function to get the weather at a particular location
    Returns:
        The location of that place
    """
    pass


a = where_is("The Golden Gate Bridge", lambda x: "good")
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
