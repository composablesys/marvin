from typing import List

from dotenv import load_dotenv

load_dotenv()

import marvin
import pydantic

class Location(pydantic.BaseModel):
    city: str
    state: str

@marvin.fn
def where_is(attraction: str) -> Location:
    """
    Args:
        attraction: the name of the attraction in some place
    Returns:
        The location of that place
    """
    pass


a = where_is("The Golden Gate Bridge")

print(a)