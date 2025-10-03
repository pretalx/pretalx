from django import forms, template

register = template.Library()


@register.simple_tag(takes_context=True)
def form_media(context):
    # The entire point of this tag is to make sure that all form media is merged
    # and then only added once per template. If this tag has been invoked before,
    # it’s a noop.
    singleton_key = "__form_media_only_once"
    flat_context = context.flatten()
    if flat_context.get(singleton_key):
        return ""
    context[singleton_key] = True

    media = forms.Media()
    for name, item in context.flatten().items():
        if isinstance(item, forms.BaseForm):
            media += item.media
        elif item and isinstance(item, (list, set)):
            first_item = next(iter(item))
            if first_item and isinstance(first_item, forms.BaseForm):
                if name == "extra_forms":
                    # This is the only current case of inherently different forms
                    # provided in a list, as these are the result of plugin hooks.
                    for subitem in item:
                        if isinstance(subitem, forms.BaseForm):
                            media += subitem.media
                else:
                    # For all other form lists, let's assume that they are formset-like,
                    # and all require the same media files.
                    media += first_item.media
    if not media._js and not media._css:
        return forms.Media()
    return (
        forms.Media(
            js=[forms.Script("common/js/formTools.js", defer="")],
            css={"all": ["common/css/_forms.css"]},
        )
        + media
    )
