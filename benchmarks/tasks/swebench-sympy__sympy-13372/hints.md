An else for re and I'm needs to be added in which prec is set to None just before line 1308 where the error arises:

```
if re == 0:..
elif re.is_number:..
else:
    reprec = None
```
Is the correct fix to set the prec to None or to raise NotImplementedError? I thought prec=None meant the number was an exact zero. 
I guess the values being None means that. The documentation in the module doesn't specify what prec=None means. 
I'd love to take this up. Can someone please tell me how to start?
Look at https://github.com/sympy/sympy/wiki/Introduction-to-contributing
