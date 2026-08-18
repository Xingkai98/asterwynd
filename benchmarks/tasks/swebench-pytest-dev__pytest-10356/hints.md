ronny has already refactored this multiple times iirc, but I wonder if it would make sense to store markers as `pytestmark_foo` and `pytestmark_bar` on the class instead of in one `pytestmark` array, that way you can leverage regular inheritance rules
Thanks for bringing this to attention, pytest show walk the mro of a class to get all markers

It hadn't done before, but it is a logical conclusion

It's potentially a breaking change.

Cc @nicoddemus @bluetech @asottile 
As for storing as normal attributes, that has issues when combining same name marks from diamond structures, so it doesn't buy anything that isn't already solved 
>so it doesn't buy anything that isn't already solved

So I mean it absolves you from explicitly walking MRO because you just sort of rely on the attributes being propagated by Python to subclasses like pytest currently expects it to.
> It's potentially a breaking change.

Strictly yes, so if we were to fix this it should go into 7.0 only.
And are there plans to include it to 7.0? The metaclass workaround does not work for me. :/ I use pytest 6.2.4, python 3.7.9
@radkujawa Nobody has been working on this so far, and 7.0 has been delayed for a long time (we haven't had a feature release this year yet!) for various reasons. Even if someone worked on this, it'd likely have to wait for 8.0 (at least in my eyes).
Re workaround: The way the metaclass is declared needs to be ported from Python 2 to 3 for it to work. 

On Fri, Jun 4, 2021, at 11:15, radkujawa wrote:
> 

> And are there plans to include it to 7.0? The metaclass workaround does not work for me. :/ I use pytest 6.2.4, python 3.7.9


> —
> You are receiving this because you authored the thread.
> Reply to this email directly, view it on GitHub <https://github.com/pytest-dev/pytest/issues/7792#issuecomment-854515753>, or unsubscribe <https://github.com/notifications/unsubscribe-auth/AAGMPRKY3A7P2EBKQN5KHY3TRCKU5ANCNFSM4RYY25OA>.

> @radkujawa Nobody has been working on this so far, and 7.0 has been delayed for a long time (we haven't had a feature release this year yet!) for various reasons. Even if someone worked on this, it'd likely have to wait for 8.0 (at least in my eyes).

thanks! 
I can not understand the solution proposed by @untitaker. In my opinion, the purpose of test inheritance is that the new test class will contain all tests from parent classes. Also, I do not think it is necessary to mark the tests in the new class with the markers from parent classes. In my opinion, every test in the new class is separate and should be explicitly marked by the user.

Example:
```python
@pytest.mark.mark1
class Test1:
    @pytest.mark.mark2
    def test_a(self):
        ...

    @pytest.mark.mark3
    def test_b(self):
        ...


@pytest.mark4
class Test2:
    @pytest.mark.mark5
    def test_c(self):
        ...


class Test3(Test1, Test):
    def test_d(self):
        ...
```

Pytest will run these tests `Test3`:
* Test3.test_a - The value of variable `pytestmark` cotians  [Mark(name="mark1", ...), Mark(name="mark2", ...)]
* Test3.test_b - The value of variable `pytestmark` cotians  [Mark(name="mark1", ...), Mark(name="mark3", ...)]
* Test3.test_c - The value of variable `pytestmark` cotians  [Mark(name="mark4", ...), Mark(name="mark5", ...)]
* Test3.test_d - The value of variable `pytestmark` is empty

@RonnyPfannschmidt What do you think?

The marks have to transfer with the mro, its a well used feature and its a bug that it doesn't extend to multiple inheritance 
> The marks have to transfer with the mro, its a well used feature and its a bug that it doesn't extend to multiple inheritance

After fixing the problem with mro, the goal is that each test will contain all the marks it inherited from parent classes?
According to my example,  the marks of `test_d` should be ` [Mark(name="mark1", ...), Mark(name="mark4", ...)]`?
Correct 
ronny has already refactored this multiple times iirc, but I wonder if it would make sense to store markers as `pytestmark_foo` and `pytestmark_bar` on the class instead of in one `pytestmark` array, that way you can leverage regular inheritance rules
Thanks for bringing this to attention, pytest show walk the mro of a class to get all markers

It hadn't done before, but it is a logical conclusion

It's potentially a breaking change.

Cc @nicoddemus @bluetech @asottile 
As for storing as normal attributes, that has issues when combining same name marks from diamond structures, so it doesn't buy anything that isn't already solved 
>so it doesn't buy anything that isn't already solved

So I mean it absolves you from explicitly walking MRO because you just sort of rely on the attributes being propagated by Python to subclasses like pytest currently expects it to.
> It's potentially a breaking change.

Strictly yes, so if we were to fix this it should go into 7.0 only.
And are there plans to include it to 7.0? The metaclass workaround does not work for me. :/ I use pytest 6.2.4, python 3.7.9
@radkujawa Nobody has been working on this so far, and 7.0 has been delayed for a long time (we haven't had a feature release this year yet!) for various reasons. Even if someone worked on this, it'd likely have to wait for 8.0 (at least in my eyes).
Re workaround: The way the metaclass is declared needs to be ported from Python 2 to 3 for it to work. 

On Fri, Jun 4, 2021, at 11:15, radkujawa wrote:
> 

> And are there plans to include it to 7.0? The metaclass workaround does not work for me. :/ I use pytest 6.2.4, python 3.7.9


> —
> You are receiving this because you authored the thread.
> Reply to this email directly, view it on GitHub <https://github.com/pytest-dev/pytest/issues/7792#issuecomment-854515753>, or unsubscribe <https://github.com/notifications/unsubscribe-auth/AAGMPRKY3A7P2EBKQN5KHY3TRCKU5ANCNFSM4RYY25OA>.

> @radkujawa Nobody has been working on this so far, and 7.0 has been delayed for a long time (we haven't had a feature release this year yet!) for various reasons. Even if someone worked on this, it'd likely have to wait for 8.0 (at least in my eyes).

thanks! 
I can not understand the solution proposed by @untitaker. In my opinion, the purpose of test inheritance is that the new test class will contain all tests from parent classes. Also, I do not think it is necessary to mark the tests in the new class with the markers from parent classes. In my opinion, every test in the new class is separate and should be explicitly marked by the user.

Example:
```python
@pytest.mark.mark1
class Test1:
    @pytest.mark.mark2
    def test_a(self):
        ...

    @pytest.mark.mark3
    def test_b(self):
        ...


@pytest.mark4
class Test2:
    @pytest.mark.mark5
    def test_c(self):
        ...


class Test3(Test1, Test):
    def test_d(self):
        ...
```

Pytest will run these tests `Test3`:
* Test3.test_a - The value of variable `pytestmark` cotians  [Mark(name="mark1", ...), Mark(name="mark2", ...)]
* Test3.test_b - The value of variable `pytestmark` cotians  [Mark(name="mark1", ...), Mark(name="mark3", ...)]
* Test3.test_c - The value of variable `pytestmark` cotians  [Mark(name="mark4", ...), Mark(name="mark5", ...)]
* Test3.test_d - The value of variable `pytestmark` is empty

@RonnyPfannschmidt What do you think?

The marks have to transfer with the mro, its a well used feature and its a bug that it doesn't extend to multiple inheritance 
> The marks have to transfer with the mro, its a well used feature and its a bug that it doesn't extend to multiple inheritance

After fixing the problem with mro, the goal is that each test will contain all the marks it inherited from parent classes?
According to my example,  the marks of `test_d` should be ` [Mark(name="mark1", ...), Mark(name="mark4", ...)]`?
Correct 
@bluetech 

it deals with
```text
In [1]: import pytest

In [2]: @pytest.mark.a
   ...: class A:
   ...:     pass
   ...: 

In [3]: @pytest.mark.b
   ...: class B: pass

In [6]: @pytest.mark.c
   ...: class C(A,B): pass

In [7]: C.pytestmark
Out[7]: [Mark(name='a', args=(), kwargs={}), Mark(name='c', args=(), kwargs={})]

```
(b is missing)
Right, I understand the problem. What I'd like to see as a description of the proposed solution, it is not very clear to me.
> Right, I understand the problem. What I'd like to see as a description of the proposed solution, it is not very clear to me.

@bluetech 
The solution I want to implement is: 
* Go through the items list. 
* For each item, I go through the list of classes from which he inherits. The same logic I do for each class until I found the object class.
* I am updating the list of marks only if the mark does not exist in the current list.
 
The existing code is incorrect, and I will now update it to work according to the logic I wrote here
@RonnyPfannschmidt 
The PR is not ready for review.
I trying to fix all the tests and after that, I'll improve the logic.
@RonnyPfannschmidt 
Once the PR is approved I'll create one commit with description 
@RonnyPfannschmidt 
You can review the PR.