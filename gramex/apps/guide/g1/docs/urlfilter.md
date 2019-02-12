# $.urlfilter

`$.urlfilter()` allows links to *update* URL query parameters instead of replacing them.

Example: Let's say the following HTML is on the page `/?city=NY`.

```html
<a class="urlfilter" href="?name=John">Link</a>
<script>
  $('body').urlfilter()
</script>
```

Clicking on any `.urlfilter` (trigger) in `body` (container) opens
`/?city=NY&name=John`. The `href=` in the `.urlfilter` link *updates* the
current page URL instead of replacing it.

`data-mode` controls the way the URL is updated by the `href`:

| URL    | href      | default    | `data-mode="add"` | `data-mode="toggle"` | `data-mode="del"` |
|--------|-----------|------------|-------------------|----------------------|-------------------|
| `?`    | `?x=1`    | `?x=1`     | `?x=1`            | `?x=1`               | `?`               |
| `?x=1` | `?x=1`    | `?x=1`     | `?x=1&x=1`        | `?`                  | `?`               |
| `?x=1` | `?y=1`    | `?x=1&y=1` | `?x=1&y=1`        | `?x=1&y=1`           | `?x=1`            |
| `?x=1` | `?x=2`    | `?x=2`     | `?x=1&x=2`        | `?x=1&x=2`           | `?x=1`            |

For example:

```html
<a class="urlfilter" href="?city=NY">                        Change ?city= to NY</a>
<a class="urlfilter" href="?city=NY" data-mode="add">        Add ?city= to NY</a>
<a class="urlfilter" href="?city=NY" data-mode="del">        Remove NY from ?city=</a>
<a class="urlfilter" href="?city=NY" data-mode="toggle">     Toggle NY in ?city=</a>

<a class="urlfilter" href="?city=NY" data-target="pushState">Change ?city= to NY using pushState</a>
<a class="urlfilter" href="?city=NY" data-target="#">        Change location.hash, i.e. #?city= to NY</a>
<a class="urlfilter" href="?city=NY" data-target="iframe">   Change iframe URL ?city= NY</a>
    <iframe src="?country=US"></iframe>
<a class="urlfilter" href="?city=NY" data-target=".block">   Use AJAX to load ?city=NY into .block</a>
    <div class="block" src="?country=US"></div>
<script>
  $('body').urlfilter()     // Activate all the .urlfilter elements above
</script>
```


## $.urlfilter attributes

When we run `$('body').urlfilter()`, the `body` is called a "container". It listens to events on "triggers", like `<a class=".urlfilter"...>`

Triggers support these attributes:

- `class="urlfilter"` indicates that this is a trigger
- `href=` updates the page URL with this link
- `data-target` defines the target where the URL is updated:
    - default: updates `window.location`
    - `"pushState"`: updates the current page using pushState
    - `"#"`: updates the `window.location.hash`
    - `".class"`: loads URL into `.class` by updating its `src=` attribute as the base URL
- `data-mode` can be
    - empty - updates existing query key with value
    - `add` - adds a new query key and value
    - `del` - deletes query key. If value exists, only deletes the (key, value) combination
    - `toggle` - toggles the query key and value combination
- `data-remove="true"`: removes query parameters without values. e.g. `?x&y=1` becomes `?y=1`
- `data-src` changes which attribute holds the current URL when `data-target=` is a selector. Default: `src`

Containers support these attributes:

- `data-selector` defines the triggers, i.e. which nodes $.urlfilter applies to. Default: `.urlfilter`
- `data-attr` changes which attribute updates the URL. Default: `href`
- You can also specify `data-mode`, `data-remove` and `data-src`, which acts as the default for all triggers.


## $.urlfilter events

- `urlfilter` is fired on the trigger when the URL is changed.
  Note: if the page is reloaded (e.g. if there is no `data-target=`),
  the page is reloaded and the event is lost. Attributes:
    - `url`: the new URL
- `load` is fired on the target when the URL is loaded -- only if the `data-target=` is a selector. Attributes:
    - `url`: the new URL

<script src="../../ui/jquery/dist/jquery.min.js"></script>
<script src="../../ui/g1/dist/g1.min.js"></script>
<script>
$(document).ready(function(){
    $("body").urlfilter({
        // "target": "pushState"
    })
    $(".codehilite").each(function(i, elem){
        console.log("great")
        $(elem).before("<div class='row'><button id='render' class='btn btn-primary btn-sm mb-2'> Render </button> </div>")
    })
    $(".row").on("click", function(){
        console.log("cool")
        var html_text = $(this).next(".codehilite").text()
        var a = html_text.indexOf("<scri")
        var b = html_text.indexOf("</scrip") + 10
        html_text = html_text.replace(html_text.slice(a, b), "")
        html_text = html_text.replace("copy", "")
        $(this).after("<div>" + html_text + "</div>")
        $(".urlfilter").each(function(elem){
            $(elem).addClass('d-block')
        })
    })
})
</script>