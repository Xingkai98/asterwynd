Bisected to 29e4cb5d45f44379aba948c2cd791b3b97210e31 (#6899 / "Remove safe_text_dupfile() and simplify EncodedFile") - cc @bluetech 
Thanks for trying the rc @hroncok and @The-Compiler for the bisection (which is very helpful). It does look like a regression to me, i.e. the previous behavior seems better. I'll take a look soon.
I've got a fix for this, PR incoming!