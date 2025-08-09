from functools import partial
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


@marvin.func_contract(
    pre=lambda comment, reply: marvin.val_contract(
        "the comment and reply must be somewhat related"
    )(comment=comment, reply=reply)
)
def process_comment(comment: str, reply: str) -> str:
    return f"comment: {comment}\nreply: {reply}"


# with temporary_settings(ai__text__disable_contract=False):
#     try:
#         process_comment("This apple is great!", "IKEA stock is down a lot")
#     except Exception as e:
#         print(e)
#     print(process_comment("This apple is great!", "I agree, but the apple is very sweet and so could be unhealthy"))


@marvin.func_contract
def reply_comment(
    processed_comment: Annotated[
        str,
        Predicate(
            marvin.val_contract("must not contain words inappropriate for children")
        ),
    ],
) -> None:
    print("The comment passed validation and is sent to the server")


with temporary_settings(ai__text__disable_contract=False):
    print("Try First Reply with Illegal Arguments")
    try:
        reply_comment("fuck this shit")
    except Exception as e:
        print("The first call is flagged as a contract violation")
        print(e)
    try:
        reply_comment("The sky is beautiful today")
    except Exception as e:
        print("The second call is flagged as a contract violation")
        print(e)


class Pilot(marvin.NaturalLangType):
    id: int
    name: str
    plane_model: str
    certificate: str
    airport: str


class AdvancedPilot(Pilot):
    @classmethod
    def natural_lang_constraints(cls) -> List[str]:
        existing = super().natural_lang_constraints()
        new_constraints = [
            "The pilot must hold the appropriate certificate for the plane_model, "
            + 'which should also be a plane that is considered "big" with paid passengers'
        ]
        return existing + new_constraints


marvin.match(
    "Noah Singer, employee number 321, is a Boeing 747 Pilot "
    "holding an Airline Transport Pilot with 1000 hours of operations. "
    "He mainly flies from KPIT. ",
    (AdvancedPilot, lambda pilot: print(pilot)),
    fall_through=lambda : print("No Advanced Pilot found")
)


# marvin.match(
#     "Peter Zhong, employee number 453 is a student pilot"
#     "flying out of KPJC with 6 hours of experience mainly in Piper Warrior",
#     (AdvancedPilot, lambda pilot: print(pilot)),
#     fall_through=lambda: print("No Advanced Pilot found"),
# )


# marvin.match(
#     "Alexa up the sound by 10 points will you? ",
#     ("Play Music by {artist}", lambda artist: artist),
#     ("Volume increase by {volume_up} units", lambda volume_up: print("System: Increasing Volume by 10 pts")),
#     ("Lights on", lambda: True),
#     ("Lights off", lambda: True),
#     (AdvancedPilot, lambda pilot: print(pilot)),
# )

# marvin.match(
#     "The recipe requires 1. Eggs 2. Tomatoes 3. Pineapples 4. Salt 5. Pepper",
#     (list, lambda ls: print(ls))
# )

if __name__ == "__main__":
    pass
