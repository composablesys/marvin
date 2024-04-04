from typing import List, Callable, Optional

from dotenv import load_dotenv

import inspect

from pydantic import Field

load_dotenv()

import marvin

@marvin.fn
def rating_for_customer(customer_profile: str) -> Callable[[str],int]:
    """
    Args:
        customer_profile: the preferences of the customer
    Returns:
        a function that specializes on the customer_profile to give a rating of a product between 1 to 10.
    """
    pass


rating_func = rating_for_customer("asian lady who cares about quality but cost is of greater concern")
rt = rating_func("A wonderful blender that is only $19, on sale from $100") # return 8


# class Location(pydantic.BaseModel):
#     city: str = Field(description="City of life ")
#     state: str = Field(description="State of affairs")
#
# Location(city="London", state="CA")
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
#
# @marvin.fn
# def where_is(attraction: str) -> Location:
#     """
#     Args:
#         attraction: the name of the attraction in some place
#     Returns:
#         The location of that place
#     """
#     pass
#
#
# a = where_is("The Golden Gate Bridge")
# #
# # print(a)


