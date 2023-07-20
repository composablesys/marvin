from enum import Enum, EnumMeta
from typing import Callable

from marvin.engine.language_models import ChatLLM, chat_llm
from marvin.engine.language_models.openai import OpenAIChatLLM
from marvin.prompts import render_prompts
from marvin.prompts.library import System, User
from marvin.utilities.async_utils import run_sync


class ClassifierSystem(System):
    content = """\
    You are an expert classifier that always choose correctly.
    
    {% if instructions %}
    {{ instructions }}

    {% endif %}
    {{ enum_class_docstring }}
    The user will provide context through text, you will use your expertise 
    to choose the best option below based on it. 
    {% for option in options %}
        {{ loop.index }}. {{ option }}
    {% endfor %}\
    """
    instructions: str = None
    options: list = []
    enum_class_docstring: str = ""


class ClassifierUser(User):
    content = """{{user_input}}"""
    user_input: str


class AIEnumMeta(EnumMeta):
    """
    A metaclass for the AIEnum class: extends the functionality of EnumMeta
    the metaclass for Python's built-in Enum class, allows additional params to be
    passed when creating an enum. These parameters are used to customize the behavior
    of the AI classifier.
    """

    def __call__(
        cls,
        value,
        names=None,
        *values,
        module=None,
        qualname=None,
        type=None,
        start=1,
        boundary=None,
        system: System = ClassifierSystem,
        user: User = ClassifierUser,
        value_getter: Callable = lambda x: x.name,
        model: ChatLLM = None,
        **kwargs,
    ):
        # If kwargs are provided, handle the missing case
        if kwargs:
            return cls._missing_(
                value, system=system, user=user, value_getter=value_getter, **kwargs
            )
        else:
            # Call the parent class's __call__ method to create the enum
            enum = super().__call__(
                value,
                names,
                *values,
                module=module,
                qualname=qualname,
                type=type,
                start=start,
                boundary=boundary,
            )

            # Set additional attributes for the AI classifier
            setattr(enum, "__system__", system)
            setattr(enum, "__user__", user)
            setattr(enum, "__model__", model)
            setattr(enum, "__value_getter__", value_getter)
            return enum


class AIEnum(Enum, metaclass=AIEnumMeta):
    """
    AIEnum is a class that extends Python's built-in Enum class.
    It uses the AIEnumMeta metaclass, which allows additional parameters to be passed
    when creating an enum. These parameters are used to customize the behavior
    of the AI classifier.
    """

    @classmethod
    def __messages__(
        cls,
        value,
        system: System = ClassifierSystem,
        user: User = ClassifierUser,
        value_getter: Callable = lambda x: x.name,
        as_dict: bool = True,
        **kwargs,
    ):
        """
        Generate the messages to be used as prompts for the AI classifier. The messages
        are created based on the system and user templates provided.
        """

        messages = render_prompts(
            [
                system(
                    enum_class_docstring=cls.__doc__ or "",
                    options=[value_getter(option) for option in cls],
                ),
                user(user_input=value),
            ],
            render_kwargs=kwargs or {},
        )

        if as_dict:
            return [
                {"role": message.role.value.lower(), "content": message.content}
                for message in messages
            ]
        return messages

    @classmethod
    def _missing_(
        cls,
        value,
        system: System = None,
        user: User = None,
        value_getter: Callable = None,
        model: ChatLLM = None,
        **kwargs,
    ):
        """
        Handle the case where a value is not found in the enum. This method is a part
        of Python's Enum API and is called when an attempt is made to access an enum
        member that does not exist.
        """

        if model is None:
            model = chat_llm(max_tokens=1, temperature=0)

        if not isinstance(model, OpenAIChatLLM):
            raise ValueError(
                "At this time, AI Classifiers rely on a tokenized approach that is only"
                " compatible with OpenAI models."
            )
        elif model.max_tokens != 1:
            raise ValueError(
                "The model must be configured with max_tokens=1 to use ai_classifier"
            )

        messages = cls.__messages__(
            value=value,
            system=system or cls.__system__,
            user=user or cls.__user__,
            value_getter=value_getter or cls.__value_getter__,
            as_dict=False,
            **kwargs,
        )

        response = run_sync(
            model.run(
                messages=messages,
                logit_bias={
                    next(iter(model.get_tokens(str(i)))): 100
                    for i in range(1, len(cls) + 1)
                },
            )
        )

        # Return the enum member corresponding to the predicted class
        return list(cls)[int(response.content) - 1]


def ai_classifier(
    cls=None,
    model: ChatLLM = None,
    system: System = ClassifierSystem,
    user: User = ClassifierUser,
    value_getter: Callable = lambda x: x.name,
):
    """
    A decorator that transforms a regular Enum class into an AIEnum class. It adds
    additional attributes and methods to the class that are used to customize the
    behavior of the AI classifier.
    """

    def decorator(enum_class):
        ai_enum_class = AIEnum(
            enum_class.__name__,
            {member.name: member.value for member in enum_class},
            system=system,
            user=user,
            value_getter=value_getter,
        )

        # Preserve the original class's docstring
        ai_enum_class.__doc__ = enum_class.__doc__ or None
        return ai_enum_class

    if cls is None:
        return decorator
    else:
        return decorator(cls)
