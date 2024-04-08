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

