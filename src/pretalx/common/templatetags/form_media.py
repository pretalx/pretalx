from contextlib import suppress

from django import forms, template

register = template.Library()

DEFAULT_FORM_MEDIA = forms.Media(
    js=[forms.Script("common/js/forms/base.js", defer="")],
    css={"all": ["common/css/forms/base.css"]},
)

DEFAULT_FORMSET_MEDIA = forms.Media(
    js=[forms.Script("orga/js/forms/formsets.js", defer="")],
)


@register.simple_tag(takes_context=True)
def form_media(context, always_base=False, extra_js=None, extra_css=None):
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
        if isinstance(item, forms.BaseFormSet):
            # with suppress(StopIteration):
            try:
                first_form = next(iter(item))
                media += first_form.media
            except StopIteration:
                with suppress(Exception):
                    media += item.empty_form.media
            media += DEFAULT_FORMSET_MEDIA + DEFAULT_FORM_MEDIA
        elif isinstance(item, forms.BaseForm):
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
    if always_base or media._js or media._css:
        media = DEFAULT_FORM_MEDIA + media
    if extra_js:
        media += forms.Media(
            js=[forms.Script(js, defer="") for js in extra_js.split(",")]
        )
    if extra_css:
        media += forms.Media(css={"all": extra_css.split(",")})
    return media
