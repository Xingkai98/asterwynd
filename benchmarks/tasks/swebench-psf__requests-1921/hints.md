We _could_ do this, but I'm actually increasingly believing that the default headers dict is the right call here.

>  We could do this, but I'm actually increasingly believing that the default headers dict is the right call here.

I'm not sure what you're talking about.

@sigmavirus24 Sorry, I had the context for this issue already. =)

Basically, we allow you to temporarily unset a header like this:

``` python
s = requests.Session()
s.get(url, headers={'Accept-Encoding': None})
```

But if you try to permanently unset a header on a `Session` in an analogous way, you get surprising behaviour:

``` python
s = requests.Session()
s.headers['Accept-Encoding'] = None
s.get(url)  # Sends the header "Accept-Encoding: None"
```

The question is, should we allow the example above to work, or should we just continue to use the `del` behaviour?

Actually, I think this is a bug in how we merge the headers before firing off a request. I'm going to send a PR in a few with a fix
