here's where this comes from: https://github.com/pytest-dev/pytest/blob/6a43c8cd9405c68e223f4c6270bd1e1ac4bc8c5f/src/_pytest/capture.py#L450-L451

Probably an easy fix to

```python
@property
def mode(self):
    return self.buffer.mode.replace('b', '')
```

Want to supply a PR with a quick test demonstrating that?

Can probably do something like:

```python
def test_stdout_mode():
    assert 'b' not in sys.stdout.mode
    assert 'b' in sys.stdout.buffer.mode
```
I'm not sure where `test_stdout_mode` belongs?
Probably `testing/test_capture.py`
Right, so this looked plausible to me:

```
diff --git a/testing/test_capture.py b/testing/test_capture.py
index 5d80eb63da..64247107fe 100644
--- a/testing/test_capture.py
+++ b/testing/test_capture.py
@@ -1189,6 +1189,11 @@ class TestStdCapture(object):
         with self.getcapture():
             pytest.raises(IOError, sys.stdin.read)
 
+    def test_stdout_mode(self):
+        with self.getcapture():
+            assert 'b' not in sys.stdout.mode
+            assert 'b' in sys.stdout.buffer.mode
+
 
 class TestStdCaptureFD(TestStdCapture):
     pytestmark = needsosdup
```

But I get this:
```
_________________________________________________________________________________________ TestStdCapture.test_stdout_mode __________________________________________________________________________________________
Traceback (most recent call last):
  File "/Users/nlevitt/workspace/pytest/testing/test_capture.py", line 1194, in test_stdout_mode
    assert 'b' not in sys.stdout.mode
AttributeError: 'CaptureIO' object has no attribute 'mode'
```

Sorry, but I don't have a lot of time to devote to this issue :-\ 

No problem, one of us can take this -- thanks for the report either way :tada: 