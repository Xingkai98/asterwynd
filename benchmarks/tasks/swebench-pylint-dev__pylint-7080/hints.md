@matusvalo Didn't you fix this recently? Or was this a case we overlooked?

https://github.com/PyCQA/pylint/pull/6528.
I will check
I am not able to replicate the issue:

```
(pylint39) matusg@MacBook-Pro:~/dev/pylint/test$ cat src/gen/test.py
import bla
(pylint39) matusg@MacBook-Pro:~/dev/pylint/test$ pylint --version
pylint 2.14.1
astroid 2.11.6
Python 3.9.12 (main, May  8 2022, 18:05:13)
[Clang 12.0.0 (clang-1200.0.32.29)]
(pylint39) matusg@MacBook-Pro:~/dev/pylint/test$ cat pyproject.toml
[tool.pylint.MASTER]
ignore-paths = [
  # Auto generated
  "^src/gen/.*$",
]
(pylint39) matusg@MacBook-Pro:~/dev/pylint/test$ pylint --recursive=y src/
(pylint39) matusg@MacBook-Pro:~/dev/pylint/test$
```
I cannot verify the issue on windows.

> NOTE: Commenting out `"^src/gen/.*$",` is yielding pylint errors in `test.py` file, so I consider that `ignore-paths` configuration is applied.
@Avasam could you provide simple reproducer for the issue?
> @Avasam could you provide simple reproducer for the issue?

I too thought this was fixed by #6528. I'll try to come up with a simple repro. In the mean time, this is my project in question: https://github.com/Avasam/Auto-Split/tree/camera-capture-split-cam-option
@matusvalo I think I've run into a similar (or possibly the same) issue. Trying to reproduce with your example:

```
% cat src/gen/test.py 
import bla

% pylint --version
pylint 2.13.9
astroid 2.11.5
Python 3.9.13 (main, May 24 2022, 21:28:31) 
[Clang 13.1.6 (clang-1316.0.21.2)]

% cat pyproject.toml 
[tool.pylint.MASTER]
ignore-paths = [
  # Auto generated
  "^src/gen/.*$", 
]


## Succeeds as expected                                                                                                                                                                                                                                                                           
% pylint --recursive=y src/

## Fails for some reason
% pylint --recursive=y .   
************* Module test
src/gen/test.py:1:0: C0114: Missing module docstring (missing-module-docstring)
src/gen/test.py:1:0: E0401: Unable to import 'bla' (import-error)
src/gen/test.py:1:0: W0611: Unused import bla (unused-import)

------------------------------------------------------------------
```

EDIT: Just upgraded to 2.14.3, and still seems to report the same.
Hmm I can reproduce your error, and now I understand the root cause. The root cause is following. The decision of skipping the path is here:

https://github.com/PyCQA/pylint/blob/3c5eca2ded3dd2b59ebaf23eb289453b5d2930f0/pylint/lint/pylinter.py#L600-L607

* When you execute pylint with `src/` argument following variables are present:
```python
(Pdb) p root
'src/gen'
(Pdb) p self.config.ignore_paths
[re.compile('^src\\\\gen\\\\.*$|^src/gen/.*$')]
```

* When you uexecute pylint with `.` argument following variables are present:
```python
(Pdb) p root
'./src/gen'
(Pdb) p self.config.ignore_paths
[re.compile('^src\\\\gen\\\\.*$|^src/gen/.*$')]
```

In the second case, the source is prefixed with `./` which causes that path is not matched. The simple fix should be to use  `os.path.normpath()` https://docs.python.org/3/library/os.path.html#os.path.normpath