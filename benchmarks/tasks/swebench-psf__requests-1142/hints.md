This was done in issue #957 - Attach Content-Length to everything.

OK, I don't think it's the right solution.
imho GET requests shouldn't contain by default 'content-length' header.

Related: geemus/excon/pull/113

There's nothing stopping you from sending data in a GET request.

At the moment the following code:
requests.get('http://amazon.com') returns 503, because the package automatically adds the header content length to the request.

If I remove that header it works fine. The thing is that currently since issue #957 this header is added automaticlly to every request and that's the cause of the problem.

Hmm, let's find some more URLs that do this.

It isn't against the HTTP/1.1 spec last I saw so I don't see why Amazon is returning a 503

GET requests don't normally include data payload in the body, and I presume their server assumes that it does because there is a content-length, but it doesn't handle the empty edge case.

It's semantically ambiguous - does a request with a Content-Length header mean "zero length body" or does it mean "no body was included in this message"?

I believe that Requests should follow the conventional wisdom, which is that most UAs do not send the Content-Length header for GET requests.

I tried to reproduce this and got weird behavior, sometimes it does work:

```
>>> r = requests.get('https://amazon.com', allow_redirects=False)
>>> print r.text
<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>301 Moved Permanently</title>
</head><body>
<h1>Moved Permanently</h1>
<p>The document has moved <a href="https://www.amazon.com/">here</a>.</p>
</body></html>

>>> print r.status_code
301
```

but sometimes it doesn't:

```
>>> print requests.get('https://amazon.com', allow_redirects=False).status_code
503

>>> print requests.get('https://amazon.com', allow_redirects=False).text
<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>301 Moved Permanently</title>
</head><body>
<h1>Moved Permanently</h1>
<p>The document has moved <a href="https://www.amazon.com/">here</a>.</p>
</body></html>
```

In fact, sometimes it seems like it might be an Amazon bug:

```
>>> print requests.get('https://amazon.com', allow_redirects=False).status_code
503
>>> print requests.get('http://amazon.com', allow_redirects=False).status_code
301
>>> print requests.get('http://amazon.com', allow_redirects=False).status_code
503
>>> print requests.get('http://amazon.com', allow_redirects=False).status_code
503
```

I'm not sure if it's relevant that I switched from ssl to plain http when I got that 301.

```
>>> print requests.__version__
1.0.3
```

Try allowing for redirects. The 301 would be followed otherwise. Printing the text for a 503 would be helpful too.

sigmavirus24: yeah, I explicitly added the allow_redirects to see what would happen: in the rare-ish cases where I get a 301 it actually does work.

And, sorry about the double-301 text, I copied the wrong thing. This is what the 503 page looks like:

```
>>> r = requests.get('http://amazon.com') ; print r.text
<html>
<head>
<meta http-equiv="Content-Type" content="text/html;charset=iso-8859-1"/>
<title>500 Service Unavailable Error</title>
</head>
<body style="padding:1% 10%;font-family:Verdana,Arial,Helvetica,sans-serif">
  <a href="http://www.amazon.com/"><img src="https://images-na.ssl-images-amazon.com/images/G/01/img09/x-site/other/a_com_logo_200x56.gif" alt="Amazon.com" width="200" height="56" border="0"/></a>
  <table>
    <tr>
      <td valign="top" style="width:52%;font-size:10pt"><br/><h2 style="color:#E47911">Oops!</h2><p>We're very sorry, but we're having trouble doing what you just asked us to do. Please give us another chance--click the Back button on your browser and try your request again. Or start from the beginning on our <a href="http://www.amazon.com/">homepage</a>.</p></td>
      <th><img src="https://images-na.ssl-images-amazon.com/images/G/01/x-locale/common/errors-alerts/product-fan-500.jpg" alt="product collage"/></th>
    </tr>
  </table>
</body>
</html>
>>> r.status_code
503
```

But, also, isn't 503 the wrong error code for a malformed request? [503 means](http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.5.4) "unable to process request due to high load". I feel like if Amazon was doing this intentionally they would return a 400 or at least something in the 4xx range.

Not that I'm saying you should ignore a problem with one of the top-10 websites on earth just because they might be being crazy.

I'm not saying we ignore it, I'm just saying it isn't against spec. And yeah, I agree that the 503 looks like it's a malformed request error. I'll mock up conditional addition for GETs tonight and see if @kennethreitz wouldn't mind the minor extra complexity.

Is there a decision or any progress with this issue?

I have encountered other sensitive servers that barf because of headers. While it would be best to get something merged into requests upstream, another option is to look at [careful-requests](https://github.com/kanzure/careful-requests) which aims to handle requests that need sensitive headers (it just monkeypatches requests). At the moment this doesn't include Content-Length on GET but that is trivial to add, I think. I hope this helps.

I frankly forgot about this, but I'll get to it tonight or tomorrow I hope. 

I'm going to go ahead and give this a shot; sigmavirus24 is going to take #1133 in the meantime.
