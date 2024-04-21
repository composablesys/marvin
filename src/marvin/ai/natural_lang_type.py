from typing import List

from pydantic import BaseModel, Field, type_adapter, model_validator

import marvin
import marvin.ai.text


class NaturalLangType(BaseModel):
    _constraints : List[str] = []

    def __declare_natural_lang__(self, instruction):
        self._constraints.append(instruction)

    def natural_lang_constraint(self):
        """
        This is a function where all child classes should override if they wish
        to declare additional natural language constraints. Note that the overridden class must
        call this method on the super() object to ensure that all constraints are populated appropriately
        __declare_natural_lang__ should be used inside of the function to declare the natural langauge constraints

        Returns:

        """
        pass

    def get_all_natural_lang_constraints(self) -> List[str]:
        self._constraints = []
        self.natural_lang_constraint()
        return self._constraints

    @model_validator(mode="after")
    def check_all_natural_lang_constraints(self):
        if marvin.settings.ai.text.disable_contract:
            return True

        return marvin.ai.text.validate_natural_lang_constraints(self, self.get_all_natural_lang_constraints())


if __name__ == "__main__":
    pass