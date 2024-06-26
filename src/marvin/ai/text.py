"""
Core LLM tools for working with text and structured data.
"""

import collections.abc
import re
import inspect
import json
import types
import typing
from collections import deque, namedtuple
from enum import Enum
from functools import partial, wraps
from typing import (
    Annotated,
    Awaitable,
    Any,
    Callable,
    GenericAlias,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
    Tuple,
)

import pydantic
from cachetools import LRUCache
from openai.types.chat import ChatCompletionMessage
from pydantic import BaseModel, model_validator, Field, create_model, validate_call

import marvin
import marvin.utilities.tools
from marvin._mappings.types import (
    cast_labels_to_grammar,
    cast_type_to_labels,
)
from marvin.ai.prompts.text_prompts import (
    CAST_PROMPT,
    CLASSIFY_PROMPT,
    EXTRACT_PROMPT,
    FUNCTION_PROMPT_FIRST_ORDER,
    FUNCTION_PROMPT_HIGHER_ORDER,
    GENERATE_PROMPT,
    MODEL_CONSTRAINT_PROMPT,
    ADDITIONAL_TYPING_CONTEXT_PROMPT,
    EXTRACT_TEXT_PROMPT,
)
from marvin.client.openai import AsyncMarvinClient, ChatCompletion, MarvinClient
from marvin.settings import temporary_settings
from marvin.types import (
    ChatRequest,
    ChatResponse,
    FunctionTool,
    BaseMessage as Message,
    ToolMessage,
    ToolOutput,
    ChatCompletionMessage,
    Predicate,
)
from marvin.utilities.asyncio import run_sync
from marvin.utilities.context import ctx
from marvin.utilities.jinja import Transcript
from marvin.utilities.logging import get_logger
from marvin.utilities.mapping import map_async
from marvin.utilities.python import CallableWithMetaData, PythonFunction
from marvin.utilities.strings import count_tokens

import docstring_parser

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

logger = get_logger(__name__)

GENERATE_CACHE = LRUCache(maxsize=1000)


class EjectRequest(Exception):
    def __init__(self, request):
        self.request = request
        super().__init__("Ejected request.")


async def generate_llm_response(
    prompt_template: str,
    prompt_kwargs: Optional[dict] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
    extra_messages: Optional[List[Message]] = None,
) -> ChatResponse:
    """
    Generates a language model response based on a provided prompt template.

    This function uses a language model to generate a response based on a provided prompt template.
    The function supports additional arguments for the prompt and the language model.

    Args:
        prompt_template (str): The template for the prompt.
        prompt_kwargs (dict, optional): Additional keyword arguments for the prompt. Defaults to None.
        model_kwargs (dict, optional): Additional keyword arguments for the language model. Defaults to None.

    Returns:
        ChatResponse: The generated response from the language model.
    """
    client = client or AsyncMarvinClient()
    model_kwargs = model_kwargs or {}
    prompt_kwargs = prompt_kwargs or {}
    extra_messages = extra_messages or []

    messages = (
        Transcript(content=prompt_template).render_to_messages(**prompt_kwargs)
        + extra_messages
    )
    request = ChatRequest(messages=messages, **model_kwargs)
    if ctx.get("eject_request"):
        raise EjectRequest(request)
    if marvin.settings.log_verbose:
        logger.debug_kv("Request", request.model_dump_json(indent=2))
    response = await client.generate_chat(request=request)
    if marvin.settings.log_verbose:
        logger.debug_kv("Response", response.model_dump_json(indent=2))
    tool_outputs = _get_tool_outputs(request, response)
    return ChatResponse(request=request, response=response, tool_outputs=tool_outputs)


def _get_tool_outputs(
    request: ChatRequest, response: ChatCompletion
) -> List[ToolOutput]:
    outputs = []
    tool_calls = response.choices[0].message.tool_calls or []
    for tool_call in tool_calls:
        tool_output = marvin.utilities.tools.call_function_tool(
            tools=request.tools,
            function_name=tool_call.function.name,
            function_arguments_json=tool_call.function.arguments,
        )
        outputs.append(
            ToolOutput(
                tool_name=tool_call.function.name,
                tool_id=tool_call.id,
                output=tool_output,
            )
        )
    return outputs


async def _generate_typed_llm_response_with_tool(
    prompt_template: str,
    type_: Union[GenericAlias, type[T]],
    tool_name: Optional[str] = None,
    prompt_kwargs: Optional[dict] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
    max_tool_usage_times: int = 1,
    existing_tools: List[FunctionTool] = None,
) -> T:
    """
    Generates a language model response based on a provided prompt template and a specific tool.

    This function uses a language model to generate a response based on a
    provided prompt template. The response is cast to a Python type using a tool
    call. The function supports additional arguments for the prompt and the
    language model.

    Args:
        prompt_template (str): The template for the prompt.
        type_ (Union[GenericAlias, type[T]]): The type of the response to
            generate.
        tool_name (str, optional): The name of the tool to use for the
            generation. Defaults to None.
        prompt_kwargs (dict, optional): Additional keyword arguments for the
            prompt. Defaults to None.
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.
        client (MarvinClient, optional): The client to use for the AI function.

    Returns:
        T: The generated response from the language model.
    """
    existing_tools = existing_tools or []
    model_kwargs = model_kwargs or {}
    prompt_kwargs = prompt_kwargs or {}
    return_tool = marvin.utilities.tools.tool_from_type(type_, tool_name=tool_name)
    model_didnt_call_function = False
    new_messages = []
    while max_tool_usage_times > 0:
        # The tool is the way to supply the response. If we are at our last generation we want to force the model's
        # hand in generating and calling the response function  alternatively, if the model didn't call any tool but
        # just generated a bunch of messages, then the next iteration we better make sure it calls the right tool
        tool_choice = (
            "auto"
            if max_tool_usage_times > 1 and not model_didnt_call_function
            else {
                "type": "function",
                "function": {"name": return_tool.function.name},
            }
        )
        model_kwargs.update(
            tools=[return_tool] + existing_tools, tool_choice=tool_choice
        )

        # adding the tool parameters to the context helps GPT-4 pay attention to field
        # descriptions. If they are only in the tool signature it often ignores them.
        prompt_kwargs["response_format"] = return_tool.function.parameters

        response = await generate_llm_response(
            prompt_template=prompt_template,
            prompt_kwargs=prompt_kwargs,
            model_kwargs=model_kwargs,
            client=client,
            extra_messages=new_messages,
        )
        new_messages.append(
            ChatCompletionMessage(
                **(response.response.choices[0].message.model_dump(exclude_none=True))
            )
        )
        tool_outputs = response.tool_outputs
        if len(tool_outputs) == 0:
            model_didnt_call_function = True

        return_res = [
            tool_output.output
            for tool_output in tool_outputs
            if tool_output.tool_name == return_tool.function.name
        ]
        if return_res:
            return return_res[0]

        new_messages.extend(
            map(
                lambda tool_output: ToolMessage(
                    content=tool_output.output, tool_call_id=tool_output.tool_id
                ),
                tool_outputs,
            )
        )
        max_tool_usage_times -= 1


async def _generate_typed_llm_response_with_logit_bias(
    prompt_template: str,
    prompt_kwargs: dict,
    encoder: Callable[[str], list[int]] = None,
    max_tokens: int = 1,
    model_kwargs: dict = None,
    client: Optional[AsyncMarvinClient] = None,
):
    """
    Generates a language model response with logit bias based on a provided
    prompt template.

    This function uses a language model to generate a response with logit bias
    based on a provided prompt template. The function supports additional
    arguments for the prompt. It also allows specifying an encoder function to
    be used for the generation.

    The LLM will be constrained to output a single number representing the
    0-indexed position of the chosen option. Therefore the labels must be
    present (and ideally enumerated) in the prompt template, and will be
    provided as the kwarg `labels`

    Args:
        prompt_template (str): The template for the prompt.
        prompt_kwargs (dict): Additional keyword arguments for the prompt.
        encoder (Callable[[str], list[int]], optional): The encoder function to
            use for the generation. Defaults to None.
        max_tokens (int, optional): The maximum number of tokens for the
            generation. Defaults to 1.
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.

    Returns:
        ChatResponse: The generated response from the language model.

    """
    model_kwargs = model_kwargs or {}

    if "labels" not in prompt_kwargs:
        raise ValueError("Labels must be provided as a kwarg to the prompt template.")
    labels = prompt_kwargs["labels"]
    label_strings = cast_type_to_labels(labels)
    grammar = cast_labels_to_grammar(
        labels=label_strings, encoder=encoder, max_tokens=max_tokens
    )
    model_kwargs.update(grammar.model_dump())
    response = await generate_llm_response(
        prompt_template=prompt_template,
        prompt_kwargs=(prompt_kwargs or {}) | dict(labels=label_strings),
        model_kwargs=model_kwargs | dict(temperature=0),
        client=client,
    )

    # the response contains a single number representing the index of the chosen
    label_index = int(response.response.choices[0].message.content)

    if labels is bool:
        return bool(label_index)

    result = label_strings[label_index]
    return labels(result) if isinstance(labels, type) else result


async def cast_async(
    data: any,
    target: type[T] = None,
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> T:
    """
    Converts the input data into the specified type.

    This function uses a language model to convert the input data into a
    specified type. The conversion process can be guided by specific
    instructions. The function also supports additional arguments for the
    language model.

    Args:
        data (str): The data to be converted.
        target (type): The type to convert the data into. If none is provided
            but instructions are provided, `str` is assumed.
        instructions (str, optional): Specific instructions for the conversion.
            Defaults to None.
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.
        client (AsyncMarvinClient, optional): The client to use for the AI
            function.

    Returns:
        T: The converted data of the specified type.
    """
    model_kwargs = model_kwargs or {}

    if target is None and instructions is None:
        raise ValueError("Must provide either a target type or instructions.")
    elif target is None:
        target = str

    # if the user provided a `to` type that represents a list of labels, we use
    # `classify()` for performance.
    if (
        get_origin(target) == Literal
        or (isinstance(target, type) and issubclass(target, Enum))
        or isinstance(target, list)
        or target is bool
    ):
        return await classify_async(
            data=data,
            labels=target,
            instructions=instructions,
            model_kwargs=model_kwargs,
            client=client,
        )

    return await _generate_typed_llm_response_with_tool(
        prompt_template=CAST_PROMPT,
        prompt_kwargs=dict(data=data, instructions=instructions),
        type_=target,
        model_kwargs=model_kwargs | dict(temperature=0),
        client=client,
    )


async def extract_async(
    data: str,
    target: type[T] = None,
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> list[T]:
    """
    Extracts entities of a specific type from the provided data.

    This function uses a language model to identify and extract entities of the
    specified type from the input data. The extracted entities are returned as a
    list.

    Note that *either* a target type or instructions must be provided (or both).
    If only instructions are provided, the target type is assumed to be a
    string.

    Args:
        data (str): The data from which to extract entities.
        target (type, optional): The type of entities to extract.
        instructions (str, optional): Specific instructions for the extraction.
            Defaults to None.
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.
        client (MarvinClient, optional): The client to use for the AI function.

    Returns:
        list: A list of extracted entities of the specified type.
    """
    if target is None and instructions is None:
        raise ValueError("Must provide either a target type or instructions.")
    elif target is None:
        target = str
    model_kwargs = model_kwargs or {}
    return await _generate_typed_llm_response_with_tool(
        prompt_template=EXTRACT_PROMPT,
        prompt_kwargs=dict(data=data, instructions=instructions),
        type_=list[target],
        model_kwargs=model_kwargs | dict(temperature=0),
        client=client,
    )


async def classify_async(
    data: str,
    labels: Union[Enum, list[T], type],
    instructions: str = None,
    additional_context: str = None,
    model_kwargs: dict = None,
    client: Optional[AsyncMarvinClient] = None,
) -> T:
    """
    Classifies the provided data based on the provided labels.

    This function uses a language model with a logit bias to classify the input
    data. The logit bias constrains the language model's response to a single
    token, making this function highly efficient for classification tasks. The
    function will always return one of the provided labels.

    Args:
        data (str): The data to be classified.
        labels (Union[Enum, list[T], type]): The labels to classify the data into.
        instructions (str, optional): Specific instructions for the
            classification. Defaults to None.
        additional_context(str, optional): Additional Context such as type information/constraints
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.
        client (AsyncMarvinClient, optional): The client to use for the AI function.

    Returns:
        T: The label that the data was classified into.
    """

    model_kwargs = model_kwargs or {}
    return await _generate_typed_llm_response_with_logit_bias(
        prompt_template=CLASSIFY_PROMPT,
        prompt_kwargs=dict(
            data=data,
            labels=labels,
            instructions=instructions,
            additional_context=additional_context,
        ),
        model_kwargs=model_kwargs | dict(temperature=0),
        client=client,
    )


async def generate_async(
    target: Optional[type[T]] = None,
    instructions: Optional[str] = None,
    n: int = 1,
    use_cache: bool = True,
    temperature: float = 1,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> list[T]:
    """
    Generates a list of 'n' items of the provided type or based on instructions.

    Either a type or instructions must be provided. If instructions are provided
    without a type, the type is assumed to be a string. The function generates at
    least 'n' items.

    Args:
        target (type, optional): The type of items to generate. Defaults to None.
        instructions (str, optional): Instructions for the generation. Defaults to None.
        n (int, optional): The number of items to generate. Defaults to 1.
        use_cache (bool, optional): If True, the function will cache the last
            100 responses for each (target, instructions, and temperature) and use
            those to avoid repetition on subsequent calls. Defaults to True.
        temperature (float, optional): The temperature for the generation. Defaults to 1.
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.
        client (AsyncMarvinClient, optional): The client to use for the AI function.

    Returns:
        list: A list of generated items.
    """

    if target is None and instructions is None:
        raise ValueError("Must provide either a target type or instructions.")
    elif target is None:
        target = str

    # cache the last 100 responses for each (target, instructions, and temperature)
    # to avoid repetition and encourage variation
    cache_key = (target, instructions, temperature)
    cached_responses = GENERATE_CACHE.setdefault(cache_key, deque(maxlen=100))
    previous_responses = []
    tokens = 0
    model = model_kwargs.get("model", None) if model_kwargs else None
    # use a token cap to avoid flooding the prompt with previous responses
    for r in list(cached_responses) if use_cache else []:
        if tokens > marvin.settings.ai.text.generate_cache_token_cap:
            continue
        tokens += count_tokens(str(r), model=model)
        previous_responses.append(r)

    # make sure we generate at least n items
    result = [0] * (n + 1)
    while len(result) != n:
        result = await _generate_typed_llm_response_with_tool(
            prompt_template=GENERATE_PROMPT,
            prompt_kwargs=dict(
                type_=target,
                n=n,
                instructions=instructions,
                previous_responses=previous_responses,
            ),
            type_=list[target],
            model_kwargs=(model_kwargs or {}) | dict(temperature=temperature),
            client=client,
        )

        if len(result) > n:
            result = result[:n]

    # don't cache the respones if we're not using the cache, because the AI will
    # see repeats and conclude they're ok
    if use_cache:
        for r in result:
            cached_responses.appendleft(r)
    return result


def fn(
    func: Optional[Callable] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[MarvinClient] = None,
    extra_render_parameters: Optional[dict] = None,
    max_tool_usage_times: int = 0,
) -> Callable:
    """
    Converts a Python function into an AI function using a decorator.

    This decorator allows a Python function to be converted into an AI function.
    The AI function uses a language model to generate its output.

    Args:
        func (Callable, optional): The function to be converted. Defaults to None.
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.
        client (MarvinClient, optional): The client to use for the AI function.
        max_tool_usage_times: The maximum number of times a tool that is passed
            in as an argument to the function could be used.

    Returns:
        Callable: The converted AI function.

    Example:
        ```python
        @fn
        def list_fruit(n:int) -> list[str]:
            '''generates a list of n fruit'''

        list_fruit(3) # ['apple', 'banana', 'orange']
        ```
    """

    if func is None:
        return partial(
            fn,
            model_kwargs=model_kwargs,
            client=client,
            extra_render_parameters=extra_render_parameters,
            max_tool_usage_times=max_tool_usage_times,
        )

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        model = PythonFunction.from_function_call(
            func, extra_render_parameters, *args, **kwargs
        )
        post_processor = marvin.settings.post_processor_fn
        prompt_template = FUNCTION_PROMPT_FIRST_ORDER
        extra_prompt_kwargs = {}

        # written instructions or missing annotations are treated as "-> str"
        if (
            isinstance(model.return_annotation, str)
            or model.return_annotation is None
            or model.return_annotation is inspect.Signature.empty
        ):
            type_ = str

        # convert list annotations into Enums
        elif isinstance(model.return_annotation, list):
            type_ = Enum(
                "Labels",
                {f"v{i}": label for i, label in enumerate(model.return_annotation)},
            )
            post_processor = lambda result: result.value  # noqa E731

        # create a callable
        elif typing.get_origin(model.return_annotation) is collections.abc.Callable:
            type_ = pydantic.create_model(
                "PromptAndName",
                prompt=(str, pydantic.Field(description="Prompt Generated")),
                function_name=(
                    str,
                    pydantic.Field(
                        description="Name of the function that "
                        "best reflect this prompt"
                    ),
                ),
            )
            args = get_args(model.return_annotation)
            prompt_template = FUNCTION_PROMPT_HIGHER_ORDER
            match args:
                case []:
                    signature = inspect.Signature([], return_annotation=None)
                case [param_annotations, return_annotations]:
                    params = [
                        inspect.Parameter(
                            f"{t.__name__.strip()}{i}",
                            inspect.Parameter.POSITIONAL_OR_KEYWORD,
                            annotation=t,
                        )
                        for i, t in enumerate(param_annotations)
                    ]
                    signature = inspect.Signature(
                        params, return_annotation=return_annotations
                    )
            # noinspection PyUnboundLocalVariable
            extra_prompt_kwargs["return_annotation"] = f"{signature}"

            post_processor = lambda result: fn(  # noqa E731
                CallableWithMetaData(
                    name=result.function_name,
                    signature=signature,
                    docstring=result.prompt,
                ),
                model_kwargs,
                client,
            )
        else:
            type_ = model.return_annotation

        func_args = filter(
            lambda param_pair: isinstance(param_pair[1], types.FunctionType),
            model.bound_parameters.items(),
        )
        parsed_doc = docstring_parser.parse(model.docstring)

        def create_tool(arg_func_pair: Tuple[str, Callable]):
            name, f = arg_func_pair
            param_docs = [
                param for param in parsed_doc.params if param.arg_name == name
            ]
            param_doc = param_docs[0].description if param_docs else None

            return marvin.utilities.tools.tool_from_function(
                fn=f, name=name, description=param_doc
            )

        tools = list(map(create_tool, func_args))

        result = await _generate_typed_llm_response_with_tool(
            prompt_template=prompt_template,
            prompt_kwargs=dict(
                with_tool=len(tools) > 0,
                fn_definition=model.definition,
                bound_parameters=model.bound_parameters,
                return_value=model.return_value,
                **extra_prompt_kwargs,
            ),
            type_=type_,
            model_kwargs=model_kwargs,
            client=client,
            existing_tools=tools,
            max_tool_usage_times=max_tool_usage_times + 1,
        )

        if post_processor is not None:
            result = post_processor(result)
        return result

    if inspect.iscoroutinefunction(func):
        return async_wrapper
    else:

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return run_sync(async_wrapper(*args, **kwargs))

        return sync_wrapper


async def validate_natural_lang_constraints_async(
    data: BaseModel,
    constraints: List[str],
    model_kwargs: Optional[dict] = None,
    client: Optional[MarvinClient] = None,
):
    result = await _generate_typed_llm_response_with_tool(
        prompt_template=MODEL_CONSTRAINT_PROMPT,
        prompt_kwargs=dict(
            data=data.model_dump_json(),
            data_type=type(data).__name__,
            constraints=constraints,
        ),
        type_=bool,
        model_kwargs=model_kwargs,
        client=client,
    )
    return result


def validate_natural_lang_constraints(
    data: any,
    constraints: List[str],
    model_kwargs: Optional[dict] = None,
    client: Optional[MarvinClient] = None,
):
    return run_sync(
        validate_natural_lang_constraints_async(
            data, constraints, model_kwargs=model_kwargs, client=client
        )
    )


def predicate(
    natural_lang_constraint="anything",
    model_kwargs: Optional[dict] = None,
    client: Optional[MarvinClient] = None,
):
    def predicate_func(*args, **kwargs) -> bool:
        """
        Check whether the data provided satisfies this constraint:

        {{ constraint }}

        Args:
            *args: args that you need to validate against the constraint
            **kwargs: kwargs that you need to validate against the constraint

        Returns:
            a bool that represents if the data satisfies the constraint given
        """

    new_f = fn(
        predicate_func,
        model_kwargs=model_kwargs,
        client=client,
        extra_render_parameters={"constraint": natural_lang_constraint},
    )
    return Predicate(func=new_f, constraint=natural_lang_constraint)


def val_contract(
    natural_lang_constraint="anything",
    model_kwargs: Optional[dict] = None,
    client: Optional[MarvinClient] = None,
):
    def wrapper(*args, **kwargs):
        if marvin.settings.ai.text.disable_contract:
            return True
        else:
            return predicate(natural_lang_constraint, model_kwargs, client)(
                *args, **kwargs
            )

    return wrapper


class Model(BaseModel):
    """
    A Pydantic model that can be instantiated from a natural language string, in
    addition to keyword arguments.
    """

    @classmethod
    async def from_text_async(
        cls,
        text: str,
        instructions: str = None,
        model_kwargs: dict = None,
        client: Optional[AsyncMarvinClient] = None,
    ) -> "Model":
        """
        Class method to create an instance of the model from a natural language string.

        Args:
            text (str): The natural language string to convert into an instance of the model.
            instructions (str, optional): Specific instructions for the conversion. Defaults to None.
            model_kwargs (dict, optional): Additional keyword arguments for the
                language model. Defaults to None.
            client (AsyncMarvinClient, optional): The client to use for the AI function.

        Returns:
            Model: An instance of the model.

        Example:
            ```python
            from marvin.ai.text import Model
            class Location(Model):
                '''A location'''
                city: str
                state: str
                country: str

            await Location.from_text_async("big apple, ny, usa")
            ```
        """
        return await cast_async(
            text,
            cls,
            instructions=instructions,
            model_kwargs=model_kwargs,
            client=client,
        )

    def __init__(
        self,
        text: Optional[str] = None,
        *,
        instructions: Optional[str] = None,
        model_kwargs: Optional[dict] = None,
        client: Optional[MarvinClient] = None,
        **kwargs,
    ):
        """
        Initializes an instance of the model.

        Args:
            text (str, optional): The natural language string to convert into an
                instance of the model. Defaults to None.
            instructions (str, optional): Specific instructions for the conversion.
            model_kwargs (dict, optional): Additional keyword arguments for the
                language model. Defaults to None.
            **kwargs: Additional keyword arguments to pass to the model's constructor.
        """
        ai_kwargs = kwargs
        if text is not None:
            ai_kwargs = cast(
                text,
                type(self),
                instructions=instructions,
                model_kwargs=model_kwargs,
                client=client,
            ).model_dump()
            ai_kwargs.update(kwargs)
        super().__init__(**ai_kwargs)


def classifier(cls=None, *, instructions=None, model_kwargs=None):
    """
    Class decorator that modifies the behavior of an Enum class to classify a string.

    This decorator modifies the __call__ method of the Enum class to use the
    `marvin.classify` function instead of the default Enum behavior. This allows
    the Enum class to classify a string based on its members.

    Args:
        cls (Enum, optional): The Enum class to be decorated.
        instructions (str, optional): Instructions for the AI on
            how to perform the classification.
        model_kwargs (dict, optional): Additional keyword
            arguments to pass to the model.

    Returns:
        Enum: The decorated Enum class with modified __call__ method.

    Raises:
        AssertionError: If the decorated class is not a subclass of Enum.
    """

    if cls is None:
        return partial(classifier, instructions=instructions, model_kwargs=model_kwargs)
    else:
        if not (isinstance(cls, type) and issubclass(cls, Enum)):
            raise TypeError(
                "Only subclasses of Enum can be decorated with @classifier."
            )

        enum_instructions = (
            f"Labels name: {cls.__name__}\nAdditional instructions: {cls.__doc__}"
        )
        instructions = instructions or enum_instructions

        def new(cls, value):
            if value in cls.__members__.values():
                return value
            elif value in {m.value for m in cls.__members__.values()}:
                return super(cls, cls).__new__(cls, value)
            else:
                return marvin.classify(
                    value, cls, instructions=instructions, **(model_kwargs or {})
                )

        cls.__new__ = new
        return cls


def model(
    type_: Union[Type[M], None] = None,
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[MarvinClient] = None,
) -> Union[Type[M], Callable[[Type[M]], Type[M]]]:
    """
    Class decorator for instantiating a Pydantic model from a string.

    This decorator allows a Pydantic model to be instantiated from a string. It's
    equivalent to subclassing the Model class.

    Args:
        type_ (Union[Type[M], None], optional): The type of the Pydantic model.
            Defaults to None.
        instructions (str, optional): Specific instructions for the conversion.
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.

    Returns:
        Union[Type[M], Callable[[Type[M]], Type[M]]]: The decorated Pydantic model.
    """
    model_kwargs = model_kwargs or {}

    def decorator(cls: Type[M]) -> Type[M]:
        class WrappedModel(Model, cls):
            @wraps(cls.__init__)
            def __init__(self, *args, **kwargs):
                super().__init__(
                    *args,
                    instructions=instructions,
                    model_kwargs=model_kwargs,
                    client=client,
                    **kwargs,
                )

        WrappedModel.__name__ = cls.__name__
        WrappedModel.__doc__ = cls.__doc__
        return WrappedModel

    if type_ is not None:
        return decorator(type_)
    return decorator


# --- Sync versions of the above functions


def cast(
    data: any,
    target: type[T] = None,
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> T:
    """
    Converts the input data into the specified type.

    This function uses a language model to convert the input data into a
    specified type. The conversion process can be guided by specific
    instructions. The function also supports additional arguments for the
    language model.

    Args:
        data (str): The data to be converted.
        target (type): The type to convert the data into. If none is provided
            but instructions are provided, `str` is assumed.
        instructions (str, optional): Specific instructions for the conversion.
            Defaults to None.
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.
        client (AsyncMarvinClient, optional): The client to use for the AI
            function.

    Returns:
        T: The converted data of the specified type.
    """
    return run_sync(
        cast_async(
            data=data,
            target=target,
            instructions=instructions,
            model_kwargs=model_kwargs,
            client=client,
        )
    )


def classify(
    data: str,
    labels: Union[Enum, list[T], type],
    instructions: str = None,
    additional_context: str = None,
    model_kwargs: dict = None,
    client: Optional[AsyncMarvinClient] = None,
) -> T:
    """
    Classifies the provided data based on the provided labels.

    This function uses a language model with a logit bias to classify the input
    data. The logit bias constrains the language model's response to a single
    token, making this function highly efficient for classification tasks. The
    function will always return one of the provided labels.

    Args:
        data (str): The data to be classified.
        labels (Union[Enum, list[T], type]): The labels to classify the data into.
        instructions (str, optional): Specific instructions for the
            classification. Defaults to None.
        additional_context(str, optional): Additional Context such as type information/constraints
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.
        client (AsyncMarvinClient, optional): The client to use for the AI function.

    Returns:
        T: The label that the data was classified into.
    """
    return run_sync(
        classify_async(
            data=data,
            labels=labels,
            instructions=instructions,
            additional_context=additional_context,
            model_kwargs=model_kwargs,
            client=client,
        )
    )


def extract(
    data: str,
    target: type[T] = None,
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> list[T]:
    """
    Extracts entities of a specific type from the provided data.

    This function uses a language model to identify and extract entities of the
    specified type from the input data. The extracted entities are returned as a
    list.

    Note that *either* a target type or instructions must be provided (or both).
    If only instructions are provided, the target type is assumed to be a
    string.

    Args:
        data (str): The data from which to extract entities.
        target (type, optional): The type of entities to extract.
        instructions (str, optional): Specific instructions for the extraction.
            Defaults to None.
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.
        client (AsyncMarvinClient, optional): The client to use for the AI function.

    Returns:
        list: A list of extracted entities of the specified type.
    """
    return run_sync(
        extract_async(
            data=data,
            target=target,
            instructions=instructions,
            model_kwargs=model_kwargs,
            client=client,
        )
    )


def generate(
    target: Optional[type[T]] = None,
    instructions: Optional[str] = None,
    n: int = 1,
    use_cache: bool = True,
    temperature: float = 1,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> list[T]:
    """
    Generates a list of 'n' items of the provided type or based on instructions.

    Either a type or instructions must be provided. If instructions are provided
    without a type, the type is assumed to be a string. The function generates at
    least 'n' items.

    Args:
        target (type, optional): The type of items to generate. Defaults to None.
        instructions (str, optional): Instructions for the generation. Defaults to None.
        n (int, optional): The number of items to generate. Defaults to 1.
        use_cache (bool, optional): If True, the function will cache the last
            100 responses for each (target, instructions, and temperature) and use
            those to avoid repetition on subsequent calls. Defaults to True.
        temperature (float, optional): The temperature for the generation. Defaults to 1.
        model_kwargs (dict, optional): Additional keyword arguments for the
            language model. Defaults to None.
        client (AsyncMarvinClient, optional): The client to use for the AI function.

    Returns:
        list: A list of generated items.
    """
    return run_sync(
        generate_async(
            target=target,
            instructions=instructions,
            n=n,
            use_cache=use_cache,
            temperature=temperature,
            model_kwargs=model_kwargs,
            client=client,
        )
    )


# --- Mapping
async def classify_async_map(
    data: list[str],
    labels: Union[Enum, list[T], type],
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> list[T]:
    return await map_async(
        fn=classify_async,
        map_kwargs=dict(data=data),
        unmapped_kwargs=dict(
            labels=labels,
            instructions=instructions,
            model_kwargs=model_kwargs,
            client=client,
        ),
    )


def classify_map(
    data: list[str],
    labels: Union[Enum, list[T], type],
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> list[T]:
    return run_sync(
        classify_async_map(
            data=data,
            labels=labels,
            instructions=instructions,
            model_kwargs=model_kwargs,
            client=client,
        )
    )


async def cast_async_map(
    data: list,
    target: type[T] = None,
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> list[T]:
    return await map_async(
        fn=cast_async,
        map_kwargs=dict(data=data),
        unmapped_kwargs=dict(
            target=target,
            instructions=instructions,
            model_kwargs=model_kwargs,
            client=client,
        ),
    )


def cast_map(
    data: list,
    target: type[T] = None,
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> list[T]:
    return run_sync(
        cast_async_map(
            data=data,
            target=target,
            instructions=instructions,
            model_kwargs=model_kwargs,
            client=client,
        )
    )


async def extract_async_map(
    data: list[str],
    target: Optional[type[T]] = None,
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> list[list[T]]:
    return await map_async(
        fn=extract_async,
        map_kwargs=dict(data=data),
        unmapped_kwargs=dict(
            target=target,
            instructions=instructions,
            model_kwargs=model_kwargs,
            client=client,
        ),
    )


def extract_map(
    data: list[str],
    target: Optional[type[T]] = None,
    instructions: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
) -> list[list[T]]:
    return run_sync(
        extract_async_map(
            data=data,
            target=target,
            instructions=instructions,
            model_kwargs=model_kwargs,
            client=client,
        )
    )


class NaturalLangType(BaseModel):
    other_information: Optional[str] = Field(
        description="Other information about the current data that could be "
        "relevant but is not otherwise captured by the other fields. "
        "Completely Optional!",
        default=None,
    )

    async def property_async(
        self,
        description: str,
        target: Type[T] = None,
        model_kwargs: Optional[dict] = None,
        client: Optional[AsyncMarvinClient] = None,
    ):
        return await extract_async(
            self,
            target=target,
            instructions=description,
            model_kwargs=model_kwargs,
            client=client,
        )

    def property(
        self,
        description: str,
        target: Type[T] = None,
        model_kwargs: Optional[dict] = None,
        client: Optional[AsyncMarvinClient] = None,
    ):
        return run_sync(
            self.property_async(
                description, target=target, model_kwargs=model_kwargs, client=client
            )
        )

    @classmethod
    def natural_lang_constraints(cls) -> List[str]:
        """
        This is a function where all child classes should override if they wish
        to declare additional natural language constraints. Note that the overridden class must
        call this method on the super() object to ensure that all constraints are populated appropriately
        from the parents unless explicitly overridden.
        existing = super().natural_lang_constraints()
        ...
        return existing + new_constraints
        """

        return []

    @model_validator(mode="after")
    def check_all_natural_lang_constraints(self):
        if marvin.settings.ai.text.disable_contract:
            return self
        constraints = self.__class__.natural_lang_constraints()
        if not constraints:
            return self
        if marvin.ai.text.validate_natural_lang_constraints(self, constraints):
            return self
        else:
            raise ValueError(
                "Natural language constraints not met:"
                + "\n".join(self.__class__.natural_lang_constraints())
                + "\n"
            )


async def match_async(
    data: any,
    *match_terms: Tuple[Union[type, str], Union[Callable, Awaitable]],
    fall_through: Optional[Callable] = None,
    model_kwargs: dict = None,
    client: Optional[AsyncMarvinClient] = None,
):
    contract_setting = marvin.settings.ai.text.disable_contract
    with temporary_settings(ai__text__disable_contract=True):
        TypeInfo = namedtuple("TypeInfo", "name schema constraints")
        defined_types: List[Type[BaseModel]] = []
        match_labels: List[str] = []
        continuations = []
        for match_term, match_func in match_terms:
            if isinstance(match_term, str):
                match_labels.append(match_term)

                async def continuation(match_term_inner, match_func_inner):
                    terms_regex = r"\{([^}]*)\}"
                    match_groups = re.findall(terms_regex, match_term_inner)
                    # noinspection PyPep8Naming
                    MatchedResult = create_model(
                        "MatchedResult",
                        **{name: (Any, None) for name in match_groups},
                    )
                    matched_result = await _generate_typed_llm_response_with_tool(
                        prompt_template=EXTRACT_TEXT_PROMPT,
                        type_=MatchedResult,
                        prompt_kwargs=dict(
                            data=data, textual_template=match_term_inner
                        ),
                        model_kwargs=model_kwargs,
                        client=client,
                    )
                    matched_dict = matched_result.dict()
                    with temporary_settings(
                        ai__text__disable_contract=contract_setting
                    ):
                        if inspect.iscoroutinefunction(match_func_inner):
                            return await match_func_inner(**matched_dict)
                        else:
                            return match_func_inner(**matched_dict)

                continuations.append((continuation, (match_term, match_func)))
            elif isinstance(match_term, type):
                typing_origin = typing.get_origin(match_term)
                typing_args = typing.get_args(match_term)
                additional_constraint = ""
                if typing_origin and typing_origin is Annotated:
                    predicates: List[Predicate] = list(
                        filter(lambda type_arg: type_arg is Predicate, typing_args)
                    )
                    if predicates:
                        additional_constraint = predicates[0].constraint
                    if typing_args:
                        match_term = typing_args[0]
                if match_term is int:
                    label = "An Integer"
                elif match_term is str:
                    label = "A String"
                elif match_term is dict:
                    label = "A Dictionary"
                elif match_term is list:
                    label = "A list"
                elif typing_origin is list:
                    of_type = typing_args[0]
                    if issubclass(of_type, BaseModel):
                        defined_types.append(of_type)
                    label = f"A list of {of_type.__name__}"
                elif typing_origin is dict:
                    index_type = typing_args[0]
                    value_type = typing_args[1]
                    if issubclass(index_type, BaseModel):
                        defined_types.append(index_type)
                    if issubclass(index_type, value_type):
                        defined_types.append(value_type)
                    label = f"A Dictionary from {index_type.__name__} to {value_type.__name__}"
                elif issubclass(match_term, BaseModel):
                    label = f"Something of {match_term.__name__} type"
                    defined_types.append(match_term)
                else:
                    raise ValueError("Unrecognized type")
                if additional_constraint:
                    final_label = (
                        f"{label} with the constraint that {additional_constraint}"
                    )
                else:
                    final_label = label
                match_labels.append(final_label)

                async def continuation(match_term_inner, match_func_inner):
                    casted = await cast_async(
                        data, match_term_inner, model_kwargs=model_kwargs, client=client
                    )
                    with temporary_settings(
                        ai__text__disable_contract=contract_setting
                    ):
                        if inspect.iscoroutinefunction(match_func_inner):
                            return await match_func_inner(casted)
                        else:
                            return match_func_inner(casted)

                continuations.append((continuation, (match_term, match_func)))
            else:
                raise ValueError("Match Term must be either a string or a type")
        if fall_through:
            match_labels.append("None of the above")

            async def continuation():
                with temporary_settings(ai__text__disable_contract=contract_setting):
                    if inspect.iscoroutinefunction(fall_through):
                        return await fall_through()
                    else:
                        return fall_through()

            continuations.append((continuation, ()))
        type_infos = []
        for defined_type in defined_types:
            type_name = defined_type.__name__
            schema = json.dumps(defined_type.model_json_schema(mode="validation"))
            constraints = []
            if issubclass(defined_type, NaturalLangType):
                constraints = defined_type.natural_lang_constraints()
            type_infos.append(TypeInfo(type_name, schema, constraints))
        typing_context = Transcript(content=ADDITIONAL_TYPING_CONTEXT_PROMPT).render(
            type_infos=type_infos
        )
        typing_context = typing_context if typing_context.strip() else None
        label = await classify_async(
            data,
            match_labels,
            additional_context=typing_context,
            model_kwargs=model_kwargs,
            client=client,
        )
        label_index = match_labels.index(label)
        await_func = continuations[label_index][0]
        args = continuations[label_index][1]
        return await await_func(*args)


def match(
    data: any,
    *match_terms: Tuple[Union[type, str], Callable],
    fall_through: Optional[Callable] = None,
    model_kwargs: dict = None,
    client: Optional[AsyncMarvinClient] = None,
):
    return run_sync(
        match_async(
            data,
            *match_terms,
            fall_through=fall_through,
            model_kwargs=model_kwargs,
            client=client,
        )
    )


def func_contract(
    func: Callable = None,
    pre: Callable = None,
    post: Callable = None,
    validate_return: bool = False,
    model_kwargs: Optional[dict] = None,
    client: Optional[AsyncMarvinClient] = None,
):
    if func is None:
        return partial(
            func_contract, pre=pre, post=post, model_kwargs=model_kwargs, client=client
        )

    inner_func = validate_call(func, validate_return=validate_return)

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if marvin.settings.ai.text.disable_contract:
            return func(*args, **kwargs)

        signature = inspect.signature(func)

        # Merge args and kwargs into a single dictionary for easier processing
        bound_arguments = signature.bind(*args, **kwargs)
        bound_arguments.apply_defaults()
        all_arguments = bound_arguments.arguments
        if pre:
            pre_sig = inspect.signature(pre)
            arg_names = list(
                filter(
                    lambda param: param.name in all_arguments.keys(),
                    pre_sig.parameters.values(),
                )
            )
            pre_dict = {key.name: all_arguments[key.name] for key in arg_names}
            condition = pre(**pre_dict)
            if not condition:
                raise ValueError("Pre condition not met")

        result = inner_func(*args, **kwargs)

        if post:
            post_sig = inspect.signature(post)
            arg_names = list(
                filter(
                    lambda param: param.name in all_arguments.keys(),
                    post_sig.parameters.values(),
                )
            )
            post_dict = {key: all_arguments[key] for key in arg_names}
            post_dict["result"] = result
            if not post(**post_dict):
                raise ValueError("Post Condition Not Met")
        return result

    return wrapper


cast_async.map = cast_async_map
cast.map = cast_map
classify_async.map = classify_async_map
classify.map = classify_map
extract_async.map = extract_async_map
extract.map = extract_map
