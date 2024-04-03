from typing import List, Callable

from dotenv import load_dotenv

import inspect

from pydantic import Field

load_dotenv()

import marvin
import pydantic

# class Location(pydantic.BaseModel):
#     city: str = Field(description="City of life ")
#     state: str = Field(description="State of affairs")
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

@marvin.fn
def rating_for_customer(customer_profile: str) -> Callable[[str],int]:
    """
    Args:
        customer_profile: the preferences of the customer
    Returns:
        a prompt that specializes on the customer_profile to give a rating of a product between 1 to 10.
    """
    pass

a = rating_for_customer("asian lady who cares about quality but cost is of greater concern")