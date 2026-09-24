Got that one too. I suspect #5831 could be the culprit, but I didn't bisect yet.
Bitten, too.. 
Importing `__init__.py` files early in a Django project bypasses the settings, therefore messing with any tuning that needs to happen before django models get instantiated.

Yes, I have bisected and found out that #5831 is the culprit when investing breakage in `flake8` when trying to move to `pytest==5.2.3`.

https://gitlab.com/pycqa/flake8/issues/594

Independently, I need to follow-up with `entrypoints` on its expected behavior.
Thanks for the report, I'll look into fixing / reverting the change when I'm near a computer and making a release to resolve this (since I expect it to bite quite a few)
this can also cause missing coverage data for `src` layout packages (see #6196)