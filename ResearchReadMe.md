# LLM Language Features 

## What I have done so far

- Higher Order Return Types








## Motivations
Recently, there have been a myriad of libraries that provide utilities for developers to integrate LMs into their programmatic environments. However, there are few experiments emphasizing how LLMs could be _organically_ integrated into a programming language. It's been envisioned by many that the field of software engineering will be revolutionized by integration with LLM and other generative AI technologies. At the macroscopic level, libraries have imposed/provided structures for prompting. However, there are few more microscopic structures that is more seamlessly integrated into programming itself. 

Of course, everything so far we are proposing for this library can be simulated with straight function calls to an LM, but we are hoping the added convenience will be helpful for developers.

The library, for the foreseeable future, will probably be mainly be used for the  [Composable System Group](https://github.com/composablesys) and [myself](https://github.com/peteryongzhong) as a way for experimentation, with the goal that if the experiments prove interesting, more energy will be devoted to make it production ready. The design of the library probably initially will lack a holistic design, but rather a collection of features. As I expand this, I am hoping there will be more holistic design opportunities that open up.

## Features Overview

Before any of the ideas are described in this section, we wish to cite [DSPy](https://github.com/stanfordnlp/dspy) and [Marvin](https://github.com/PrefectHQ/marvin), as they inspired many of the features contained herein. In pa

### Natural Language Functions (TODO)

Functions are the most basic unit in which a programmer could interact with the LM. We take much inspiration from Marvin in this case since we feel their design decisions are very intuitive.

```python

import lmlang

@lmlang.fn
def cuisine_recs(spiciness : int, food_likes: list[str] ) -> str:
    lmlang.input_describe(spiciness, "the spice tolerance")
    lmlang.input_describe(food_likes, "a list of foods that are currently like")
    lmlang.output_describe("cuisine that is good to try")
```

```python
import lmlang

@lmlang.fn
def cuisine_recs(spiciness : int, food_likes: list[str] ) -> str:
    """
    What cuisine is good to try given the `spiciness` and `food_likes` which denotes my preferences right now?
    """
```


#### Why not higher order as well? (TODO)

In programming, especially in a functional programming setting, programmers use higher-ordered functions to specialize the behavior of their program by being more abstract. There is no reason why the same design patterns could not be extended to LMs. 

One understanding of a prompt is a high level fuzzy specification for some high level natural computation process, such as the one shown in the previous example. We could extend the same process here.

In this example, let's assume that the CustomerProfile class and the Product class will have some descriptions, the tool should automatically integrate them into the prompt.

```python
@lmlang.fn
def rating_for_customer(customer_profile: CustomerProfile) -> Callable[[Product], int]:
    """
    :returns: A function from a product to a rating that the customer would likely given based on their profile
    """
```

Another use case of higher-ordered functions might be through the use of a function as an argument to a natural language function. 

Often the argument that is a function can essentially serve as some "tool" that the LM has access to. This tool could be something that is defined as a standard programmatic function, but it's conceivable that it might also be another LM powered function.

```python
@lmlang.fn
def outfit_match(items_of_clothing: List[Clothes], client_comment : Callable[[Clothes], str], scenario:str) -> List[Clothes]:
    """
    As a fashion designer, for a given `scenario` please pick a suitable outfit from the `item_of_clothing`, taking into account \
                         of the `client_comment`.
    """
```

```python
@lmlang.fn
def landing_airport(airports : List[Airport], weather: Callable[[Airport], str]) -> Airport:
    """
    I am a VFR student pilot, where should I land without breaking FAA regulations?
    
    :param airports: List of Airports that I am considering landing
    :param weather: A function that returns the current weather conditions (METAR) and (TAF) at a particular airport
    :returns: A function from a product to a rating that the customer would likely given based on their profile
    """
```


#### Natural Predicate (TODO)

This serves as a sugar for Natural Language functions, but it can be really helpful in some cases.

```python
ls = [dress1, dress2, dress3 ....]

filter(lmlang.predicate("Dresses suitable for formal occasions."), ls)
```

At times, it will be helpful to have an explanation for why a predicate succeeded or failed. 


```python
ls = [dress1, dress2, dress3 ....]

filter(lmlang.explainable_predicate("Dresses suitable for formal occasions."), ls)
# behave the same as the previous example

result = lmlang.explainable_predicate("Dresses suitable for formal occasions.")(casual_dress) # return an lmlang.Explainable Object
if not result:
    print("dress is not suitable") # triggered here
    print(result.reason ) 

```

or other convenient function such as :

```python
res = lmlang.quickfunc("what is the earth's only satellite?") #the moon
air_space = AirSpace.ClassD 
res = lmlang.quickfunc("What is the minimum visibility in an VFR flight from this class of airpace during the day in statute miles", air_space) #3 
```


#### Natural Contracts (TODO)

Software contracts are a very good way of ensuring invariants are not broken. Especially during dev time, and even in production, contracts help programmers by concisely specifying the pre and post conditions. Sometimes these conditions can be spelled out programmtically, say using a contract library such as [PyContract](https://andreacensi.github.io/contracts/) would be quite nice in terms of this specification. 

Unfortunately, PyContract has long since fell out of maintenance. But Pydantic is a library that has many intersecting features with PyContract that could be helpful. 

This is especially helpful in the context of https://typing.readthedocs.io/en/latest/spec/qualifiers.html#annotated and https://docs.pydantic.dev/latest/concepts/types/#custom-types, which allows for the annotation of custom typing constraints. We propose combining such annotations and type checking validation capabilities of Pydantic and the introduction of LLM as a special validator into the contract system.

```python
PositiveInt = Annotated[int, Gt(0)]
RespectfulComment = Annotated[str, lmlang.annotate("Must be respectful")]

@contract
def process_comment(times : PositiveInt, comment: RespectfulComment) -> bool:
    pass
```
At times we might need compositional constraints
```python
PositiveInt = Annotated[int, Gt(0)]
RespectfulComment = Annotated[str, lmlang.annotate("Must be respectful")]

@contract(precond=lmlang.compositional_contract("comment", "reply", "the reply to the comment must be related and not off topic"))
def process_comment(comment: RespectfulComment, reply:str) -> bool:
    pass
```
For post conditions it will be very similar. Where the LM could evaluate if the function produced the correct result based on either just the result
or the result parameterized by arguments. 

### Code Generation 

Code Generation refer to the process by which a language model, rather than directing producing the answer to some question, produces a code segment that achieves the desired outcomes. A very related concept in prompting is the notion of [Program of Thoughts](https://arxiv.org/abs/2211.12588). Especially for predictable tasks, the LM may be able to understand the high level abstract computational notion of the desired task, better than the actual calculation, which may involve numerical tasks which the LMs tend to perform poorly on.

We have already seen how we could wrap the LM around a function that is governed by its natural language descriptions above. The interface exposes a direct opportunity for code generation. 

```python
import lmlang

@lmlang.fn(codegen=True)
def user_eligible(user: User ) -> bool:
    lmlang.func_describe("This function should check if the user is eligible for discount by checking if it's either a student or teacher and has never had an account delinquency")
```
The LM might generate a code to the effect of:

```python

def user_eligible(user: User ) -> bool:
    if user.status not in  ["student", "teacher"]:
        return False
    return len(user.delinquencies) == 0
```

Or sometimes we need to instruct the LM for a partial generation if the structure of the code is fixed, but there are "holes" where the programmer only specifies natural language descriptions:

```python
import lmlang

@lmlang.partial(codegen=True)
def send_marketing_emails(users: User) -> bool:
    final_user = []
    for user in users:
        lmlang.incontext_gen("if the `user` is eligible for discount by checking if it's either a student or teacher and has never had an account delinquency, add it to the `final_user` list")
    lmlang.incontext_gen("send an email using the template EmailTemplate.Marketing to all the `final_user` informing they got a promotion.")
```

While this is something that could be done at runtime and memoized for future use, it's not really helpful since the programmer would likely wish to refine the generated code. 

We propose that in addition to the runtime behavior, we support integration with popular IDEs such as VScode and/or PyCharm that could allow the user to directly view the generated code live and refine it as they code.

Furthermore, as software engineers, we recognize the importance of unit testing in the developmental process. In recent LM research results, there has also been very encouraging results that demonstrate the ability for unit test to augment the generation process. In recognition of these traits, we believe the programmer should have the ability to use unit testing both to leverage it for correctness assessments, but also for the generation process.

```python
@lmlang.fn(codegen=True, unittest=Tests.UserEligibleTest)
def user_eligible(user: User ) -> bool:
    lmlang.func_describe("This function should check if the user is eligible for discount by checking if it's either a student or teacher and has never had an account delinquency")
```

Even if you do not provide `codegen=True`, the library can still "try" to take advantage of the unittest by using it as demonstrations in the ICL sense:

```python
@lmlang.fn(codegen=True)
def user_eligible(user: User ) -> bool:
    lmlang.func_describe("This function should check if the user is eligible for discount by checking if it's either a student or teacher and has never had an account delinquency")
```


### Natural Language Types And Natural Language Specs For Types

"Types" and data models are concepts that are intimately familiar with developers. However, traditional types are rigid, and for the purposes of LM interactions, can be quite restrictive. This could be a result of the fact that unstructured natural language data is forced and serialized into structured format. Whilst such structure is certainly desirable, for the intermediate LM steps, it could be desirous to allow the LM to be a bit more unstructured.

What does this mean in terms of concrete class design? 

We first propose to introduce a contract system for classes built upon Pydantic that augment the existing type annotation validation system with the ability to specify natural language constraints. Secondly, we propose that classes should have an optional natural langauge metadata, which, if generated through some intermediate process, could be populated by the LM for future use. 

This is partially achieved through the annotations shown above which allows for natural langauge descriptions. However, we could extend this by allowing for interfield dependencies to be specified, both in natural language and programmatically:

```python
@classcontract{
    [lmlang.compositional_contract("plane_model", "airport", "the airport must be big enough for support the plane")]
}
class Pilot:
    """
    A pilot is a class describing a pilot who files at an airport 
    """
    id: int
    name : str
    plane_model : str
    airport : str
```

An idea that naturally falls out of this set up is the notion of a natural language inheritance scheme:

```python
@classcontract{
    [lmlang.compositional_contract("plane_model", "The plane_model must be a big plane with jet engines")]
}
class BigBoyPilot(Pilot):
    pass
```

Why would this be helpful? The natural language classification of object hierarchy could be helpful for moderating the functions located in the subclass. In effect, with the understanding that the natural langauge restriction is in place, it opens the function up to more possibilities since it's a more constrained set of values.  

#### Casting

For users of C++, the concept of dynamic casting, while somewhat cursed, has value from a software engineering perspective. 

LMs could moderate the process of casting and dyncast.

For instance:
```python
lmlang.try_cast(cessna_172_pilot, BigBoyPilot ) # None 
lmlang.try_cast(boeing747_pilot, BigBoyPilot) # a BigBoyPilot object
```
We could even use natural language casting as a way to extract information by converting from one model to another model. 

```python
class Food:
    brand :str
    ingredient: List[str]
    # ...

class Nutrition:
    """Whether it's a good source of nutrients"""
    vitaminA: bool
    calcium :bool 
    # ....

lmlang.try_cast(huel, Nutrition, "Provide a nutritional breakdown of the food please.")
```
#### Selecting

Sometimes the property a programmer want is not necessarily the property that is explicitly specified. 

Therefore it could be helpful to use natural langauge command as if you are getting a property.

```python
ceasna_172.ai_property("Number of Engines") # return 1
boeing737max.ai_property("Number of Emergency Exits") # undefined behavior
```

### Natural Language Pattern Matching 

Augment the syntax of Python's pattern matching to use natural language. 

Python's current pattern matching syntax and semantics is described in details [here](https://docs.python.org/3/reference/compound_stmts.html#match). The proposed syntax here will likely need to run through a source-to-source pre-compilation that will ensure the compiled code adheres to the features that are currently available. 

We will use `a` as a prefix for AI interpreted matching 

For instance: 
```python
user_command = "I want to turn the lamp on please thanks!:)"

match user_command:
    case a'Lights on':
        pass
    case a'Lights off':
        pass
    case a'Speaker On':
        pass
    # ..... Other cases
```
An extremely powerful concept in functional programming pattern matching that has been adopted by the Python community is the ability to extract information in a particular object through a predefined patterns. Right now, these patterns are all programmatic patterns, but with LMs, we could introduce natural language decompositions. 
```python
match user_command:
    case a'Volume increase by {volume_up} units':
        volumn += volumn_up
    case a'Lights on':
        pass
    case a'Lights off':
        pass
    case a'Speaker On':
        pass
    # ..... Other cases
```

```python
match transportation_devices:
    case Plane(a'Number of Engine' as engine_num):
        pass
    case Cars(a'Number of Cylindars' as cylindar_num):
        pass
```

Of course, this can be combined with the try_cast semantics earlier: 

        
```python
match food:
    case CastedType(Nutrient(vitaminA = va), "Provide a nutritional breakdown of the food please."):
        pass

```

### Mocking and Unit-testing 

IDE support is critical here.

#### Mocking and Synthetic Generation

Synthetically generating 

```python
lmlang.mock(User, "Adam who is great at swimming")

```

#### Direct unit test generation

Cite 10.1109/TSE.2023.3334955 . Syntax TBD, but developers should specify the function they want to test and some properties in natural language. 

### What can we do with loops?

Who knows

## Prompt Agnostic and Prompting Technique incorporation

We are thinking maybe we could use `with` blocks to specify concrete strategies like COT?
