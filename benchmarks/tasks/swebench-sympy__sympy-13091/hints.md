Classes are generally required to subclass from Basic to interoperate with SymPy. 

What happens in the test suite if you change it to NotImplemented?
Subclassing won't help in this case, it will just move the problem to line 319 (returns ``False`` if sympy types are different). Which is to say, ``NotImplemented`` should be returned in this case too in order to maintain symmetric relations. As a bonus, there may be potential for cleaning up some of the rich comparison methods throughout the package (when some specialized type deems itself comparable to a more general type, this will only have to be supported by the specialized class -- the general class won't have to know anything about it).

Regarding the interoperability of types without any inheritance relationship, consider the following example:
```python
>>> from sympy import sympify
>>> two_sympy = sympify(2.0)
>>> two_float = 2.0
>>> two_sympy == two_float
True
>>> two_float == two_sympy
True
>>> two_sympy.__eq__(two_float)
True
>>> two_float.__eq__(two_sympy)
NotImplemented
```
The reason a sympy ``Float`` and a python ``float`` compare symmetrically is twofold:
* sympy implements support for this in ``Float.__eq__``, and
* python's internal ``float.__eq__`` returns ``NotImplemented`` when it sees apples and oranges.

I'll have a look at the tests.