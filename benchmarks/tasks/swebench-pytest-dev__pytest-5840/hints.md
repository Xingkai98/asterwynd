Can you show the import line that it is trying to import exactly? The cause might be https://github.com/pytest-dev/pytest/pull/5792.

cc @Oberon00
Seems very likely, unfortunately. If instead of using `os.normcase`, we could find a way to get the path with correct casing (`Path.resolve`?) that would probably be a safe fix. But I probably won't have time to fix that myself in the near future 😟
A unit test that imports a conftest from a module with upppercase characters in the package name sounds like a good addition too.
This bit me too.

* In `conftest.py` I `import muepy.imageProcessing.wafer.sawStreets as sawStreets`.
* This results in `ModuleNotFoundError: No module named 'muepy.imageprocessing'`.  Note the different case of the `P` in `imageProcessing`.
* The module actually lives in 
`C:\Users\angelo.peronio\AppData\Local\Continuum\miniconda3\envs\packaging\conda-bld\muepy_1567627432048\_test_env\Lib\site-packages\muepy\imageProcessing\wafer\sawStreets`.
* This happens after upgrading form pytest 5.1.1 to 5.1.2 on Windows 10.

Let me know whether I can help further.

### pytest output
```
(%PREFIX%) %SRC_DIR%>pytest --pyargs muepy
============================= test session starts =============================
platform win32 -- Python 3.6.7, pytest-5.1.2, py-1.8.0, pluggy-0.12.0
rootdir: %SRC_DIR%
collected 0 items / 1 errors

=================================== ERRORS ====================================
________________________ ERROR collecting test session ________________________
..\_test_env\lib\site-packages\_pytest\config\__init__.py:440: in _importconftest
    return self._conftestpath2mod[conftestpath]
E   KeyError: local('c:\\users\\angelo.peronio\\appdata\\local\\continuum\\miniconda3\\envs\\packaging\\conda-bld\\muepy_1567627432048\\_test_env\\lib\\site-packages\\muepy\\imageprocessing\\wafer\\sawstreets\\tests\\conftest.py')

During handling of the above exception, another exception occurred:
..\_test_env\lib\site-packages\_pytest\config\__init__.py:446: in _importconftest
    mod = conftestpath.pyimport()
..\_test_env\lib\site-packages\py\_path\local.py:701: in pyimport
    __import__(modname)
E   ModuleNotFoundError: No module named 'muepy.imageprocessing'

During handling of the above exception, another exception occurred:
..\_test_env\lib\site-packages\py\_path\common.py:377: in visit
    for x in Visitor(fil, rec, ignore, bf, sort).gen(self):
..\_test_env\lib\site-packages\py\_path\common.py:429: in gen
    for p in self.gen(subdir):
..\_test_env\lib\site-packages\py\_path\common.py:429: in gen
    for p in self.gen(subdir):
..\_test_env\lib\site-packages\py\_path\common.py:429: in gen
    for p in self.gen(subdir):
..\_test_env\lib\site-packages\py\_path\common.py:418: in gen
    dirs = self.optsort([p for p in entries
..\_test_env\lib\site-packages\py\_path\common.py:419: in <listcomp>
    if p.check(dir=1) and (rec is None or rec(p))])
..\_test_env\lib\site-packages\_pytest\main.py:606: in _recurse
    ihook = self.gethookproxy(dirpath)
..\_test_env\lib\site-packages\_pytest\main.py:424: in gethookproxy
    my_conftestmodules = pm._getconftestmodules(fspath)
..\_test_env\lib\site-packages\_pytest\config\__init__.py:420: in _getconftestmodules
    mod = self._importconftest(conftestpath)
..\_test_env\lib\site-packages\_pytest\config\__init__.py:454: in _importconftest
    raise ConftestImportFailure(conftestpath, sys.exc_info())
E   _pytest.config.ConftestImportFailure: (local('c:\\users\\angelo.peronio\\appdata\\local\\continuum\\miniconda3\\envs\\packaging\\conda-bld\\muepy_1567627432048\\_test_env\\lib\\site-packages\\muepy\\imageprocessing\\wafer\\sawstreets\\tests\\conftest.py'), (<class 'ModuleNotFoundError'>, ModuleNotFoundError("No module named 'muepy.imageprocessing'",), <traceback object at 0x0000018F0D6C9A48>))
!!!!!!!!!!!!!!!!!!! Interrupted: 1 errors during collection !!!!!!!!!!!!!!!!!!!
============================== 1 error in 1.32s ===============================
```